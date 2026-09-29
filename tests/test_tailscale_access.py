import pytest
from dataclasses import replace
from fastapi.testclient import TestClient
from mapwalker.app import create_app
from mapwalker.auth import AccessConfig, SESSION_COOKIE

CONFIG=AccessConfig(True,'https://mapwalker.example.ts.net',emails=('owner@gmail.com',),mode='tailscale')
HEADERS={'Tailscale-User-Login':'owner@gmail.com','X-Forwarded-Proto':'https'}

@pytest.fixture
def private(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[],access_config=CONFIG)
    with TestClient(app,base_url=CONFIG.origin,client=('127.0.0.1',40000)) as c:
        yield app,c

def test_serve_identity_bootstraps_secure_session_and_csrf(private):
    app,c=private
    assert c.get('/').status_code==403
    r=c.get('/',headers=HEADERS);assert r.status_code==200
    cookie=r.headers['set-cookie']
    assert all(x in cookie for x in ('Secure','HttpOnly','SameSite=lax'))
    me=c.get('/auth/me',headers=HEADERS).json()
    assert me['mode']=='tailscale' and me['email']=='owner@gmail.com'
    assert c.post('/api/worker/pause',json={'paused':True},headers=HEADERS).status_code==403
    h={**HEADERS,'Origin':CONFIG.origin,'X-CSRF-Token':me['csrf']}
    assert c.post('/api/worker/pause',json={'paused':True},headers=h).status_code==200
    assert c.post('/api/worker/pause',json={'paused':False},headers={**h,'Origin':'https://evil.test'}).status_code==403
    assert app.state.store.status()['paused']
    # Even a valid session cookie is useless without the Serve identity.
    assert c.get('/api/status').status_code==403
    assert c.get('/api/status',headers={**HEADERS,'Tailscale-User-Login':'stranger@gmail.com'}).status_code==403
    assert c.get('/auth/config',headers=HEADERS).json()=={'enabled':True,'mode':'tailscale'}
    assert c.get('/auth/login',headers=HEADERS,follow_redirects=False).status_code==307
    assert c.post('/auth/logout',headers=h).status_code==400

def test_headers_from_nonloopback_peer_are_rejected(private):
    app,_=private
    with TestClient(app,base_url=CONFIG.origin,client=('192.168.1.20',40000)) as c:
        assert c.get('/',headers=HEADERS).status_code==403

def test_wrong_host_or_forwarded_scheme_is_rejected(private):
    _,c=private
    assert c.get('/',headers={**HEADERS,'Host':'localhost'}).status_code==403
    assert c.get('/',headers={**HEADERS,'X-Forwarded-Proto':'http'}).status_code==403
    assert c.get('/',headers={'Tailscale-User-Login':'owner@gmail.com'}).status_code==403

@pytest.mark.parametrize('changes',[{'origin':'https://example.com'},{'emails':()},{'emails':('*@gmail.com',)},{'subjects':('123',)}])
def test_private_config_fails_closed(changes):
    with pytest.raises(ValueError):replace(CONFIG,**changes).validate()
