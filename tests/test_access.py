"""Authentication boundary tests use isolated data and RSA keys, never a runtime bypass."""
import json
import time
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from google.auth import crypt, jwt

from mapwalker.app import create_app
from mapwalker.auth import AccessConfig, SESSION_COOKIE, LOGIN_COOKIE, digest

CONFIG=AccessConfig(True,'https://map.example.test','123-test.apps.googleusercontent.com',('owner@gmail.com',))


@pytest.fixture
def guarded(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[],access_config=CONFIG)
    with TestClient(app,base_url=CONFIG.origin,follow_redirects=False) as client:
        yield app,client


@pytest.fixture
def signing_key():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    return crypt.RSASigner.from_string(pem,key_id='isolated-test-key'),public.decode()


def sign_in(app,client,key,**changes):
    signer,public=key
    # Only the certificate HTTP response is replaced. Google's actual RSA verifier runs.
    class CertResponse:
        status=200
        data=json.dumps({'isolated-test-key':public}).encode()
    app.state.access.transport=lambda *args,**kwargs:CertResponse()
    nonce=client.get('/auth/config').json()['nonce']
    claims=dict(aud=CONFIG.client_id,iss='https://accounts.google.com',iat=int(time.time())-2,
                exp=int(time.time())+300,sub='100000000000000000001',email='owner@gmail.com',email_verified=True,nonce=nonce)
    claims.update(changes)
    token=jwt.encode(signer,claims).decode()
    return client.post('/auth/google',json={'credential':token},headers={'Origin':CONFIG.origin,'X-CSRF-Token':nonce})


@pytest.mark.parametrize('path',['/','/app.js','/access.js','/style.css','/vendor/leaflet.js','/api/status',
    '/api/browse','/api/pois/1','/api/pois/1/image','/api/export','/api/tiles/JM50K_1916/16/54895/28092',
    '/api/osm/context','/evidence/viewer/report.html','/evidence/viewer/mobile-map.png','/docs','/openapi.json'])
def test_every_private_surface_requires_session(guarded,path):
    _,client=guarded
    response=client.get(path,headers={'X-Forwarded-For':'127.0.0.1','CF-Access-Authenticated-User-Email':'owner@gmail.com'})
    assert response.status_code==401
    assert response.headers['Cache-Control']=='no-store'


def test_login_redirect_and_public_assets(guarded):
    _,client=guarded
    assert client.get('/',headers={'Accept':'text/html'}).headers['location']=='/auth/login?next=%2F'
    for path in ['/auth/login','/auth/login.css','/auth/login.js','/healthz']:
        response=client.get(path)
        assert response.status_code==200 and response.headers['Cache-Control']=='private, no-store'
    assert client.get('/healthz').json()['authentication_required'] is True


def test_signed_login_secure_session_csrf_logout_and_replay(guarded,signing_key):
    app,client=guarded
    result=sign_in(app,client,signing_key)
    assert result.status_code==200
    raw=client.cookies.get(SESSION_COOKIE)
    cookie=result.headers.get_list('set-cookie')[0]
    for expected in ['HttpOnly','Secure','SameSite=lax','Path=/','Max-Age=28800']:assert expected in cookie
    assert 'Domain=' not in cookie
    with app.state.access.connect() as db:
        assert db.execute('SELECT token FROM sessions').fetchone()[0]==digest(raw)
    assert client.get('/').status_code==200
    assert client.get('/api/status').status_code==200
    me=client.get('/auth/me').json();assert me['email']=='owner@gmail.com'
    for headers in [{},{'Origin':CONFIG.origin},{'Origin':'https://evil.test','X-CSRF-Token':me['csrf']}]:
        assert client.post('/api/worker/pause',json={'paused':True},headers=headers).status_code==403
    headers={'Origin':CONFIG.origin,'X-CSRF-Token':me['csrf']}
    assert client.post('/api/worker/pause',json={'paused':True},headers=headers).status_code==200
    assert client.post('/auth/logout',headers=headers).status_code==200
    assert client.get('/api/status').status_code==401
    client.cookies.set(SESSION_COOKIE,raw)
    assert client.get('/api/status').status_code==401


@pytest.mark.parametrize('changes,status',[
    ({'email':'other@gmail.com'},403),({'email_verified':False},403),
    ({'aud':'wrong.apps.googleusercontent.com'},401),({'iss':'https://evil.test'},401),
    ({'exp':int(time.time())-100},401),({'iat':int(time.time())+10000},401),
    ({'nonce':'wrong-nonce'},401),({'sub':''},401)])
def test_signed_but_unacceptable_identity(guarded,signing_key,changes,status):
    app,client=guarded
    assert sign_in(app,client,signing_key,**changes).status_code==status
    assert client.get('/api/status').status_code==401


def test_wrong_signature_nonce_replay_and_login_csrf(guarded,signing_key):
    app,client=guarded
    nonce=client.get('/auth/config').json()['nonce']
    assert client.post('/auth/google',json={'credential':'bad'},headers={'Origin':CONFIG.origin}).status_code==403
    assert client.post('/auth/google',json={'credential':'bad'},headers={'Origin':'https://evil.test','X-CSRF-Token':nonce}).status_code==403
    # Malformed token must be rejected; certificate fetch is deterministic.
    class CertResponse:
        status=200
        data=json.dumps({'isolated-test-key':signing_key[1]}).encode()
    app.state.access.transport=lambda *args,**kwargs:CertResponse()
    headers={'Origin':CONFIG.origin,'X-CSRF-Token':nonce}
    assert client.post('/auth/google',json={'credential':'bad'},headers=headers).status_code==401
    assert client.post('/auth/google',json={'credential':'bad'},headers=headers).status_code==401
    assert client.get('/api/status').status_code==401
    # A complete JWT signed by a different key also fails Google's signature check.
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pem=other.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    assert sign_in(app,client,(crypt.RSASigner.from_string(pem,key_id='isolated-test-key'),signing_key[1])).status_code==401


def test_expiry_revocation_restart_and_host(guarded,signing_key,tmp_path):
    app,client=guarded
    assert sign_in(app,client,signing_key).status_code==200
    raw=client.cookies.get(SESSION_COOKIE)
    from mapwalker.auth import Access
    restarted=Access(tmp_path,CONFIG)
    assert restarted.session(raw)
    restarted.config=replace(CONFIG,emails=('someone@gmail.com',))
    assert restarted.session(raw) is None
    assert client.get('/api/status',headers={'Host':'evil.test'}).status_code==400
    with app.state.access.connect() as db:db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
    assert client.get('/api/status').status_code==401


def test_unverified_external_email_requires_stable_google_subject(tmp_path):
    config=replace(CONFIG,emails=('owner@external.test',))
    assert not config.allowed('owner@external.test','123',False)
    assert replace(config,subjects=('123',)).allowed('owner@external.test','123',False)
    assert config.allowed('owner@external.test','123',True)


@pytest.mark.parametrize('changes',[{'origin':''},{'origin':'http://example.test'},{'origin':'https://example.test/path'},
    {'origin':'https://example.test/'},{'origin':None},{'client_id':''},{'client_id':None},
    {'emails':()},{'emails':('*@gmail.com',)},{'subjects':('not-a-subject',)}])
def test_incomplete_or_unsafe_public_config_fails_closed(tmp_path,changes):
    with pytest.raises(ValueError):create_app(tmp_path,worker_enabled=False,registry=[],access_config=replace(CONFIG,**changes))
    assert not (tmp_path/'mapwalker.sqlite3').exists()


def test_local_listener_cannot_be_used_as_proxy_target(tmp_path):
    with TestClient(create_app(tmp_path,worker_enabled=False,registry=[])) as client:
        assert client.get('/auth/me').json()=={'enabled':False}
        assert client.get('/api/status').status_code==200
        for header in ['Forwarded','X-Forwarded-For','X-Forwarded-Host','CF-Connecting-IP']:
            assert client.get('/api/status',headers={header:'anything'}).status_code==403


def test_challenge_expiry_and_rate_limit(guarded):
    app,client=guarded
    nonce=client.get('/auth/config').json()['nonce']
    with app.state.access.connect() as db:db.execute('UPDATE challenges SET expires=?',(time.time()-1,))
    assert client.post('/auth/google',json={'credential':'bad'},headers={'Origin':CONFIG.origin,'X-CSRF-Token':nonce}).status_code==401
    for _ in range(59):assert client.get('/auth/config').status_code==200
    assert client.get('/auth/config').status_code==429


def test_public_replica_does_not_recover_active_osm_work(tmp_path):
    from mapwalker.osm import OSMContext
    osm=OSMContext(tmp_path)
    osm.request(121.55,24.86)
    with osm.connect() as db:db.execute("UPDATE requests SET state='running'")
    create_app(tmp_path,worker_enabled=False,registry=[],access_config=CONFIG)
    with osm.connect() as db:assert db.execute('SELECT state FROM requests').fetchone()[0]=='running'
