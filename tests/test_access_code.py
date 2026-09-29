import secrets
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from mapwalker.app import create_app
from mapwalker.auth import AccessConfig, SESSION_COOKIE, LOGIN_COOKIE, digest


@pytest.fixture
def private(tmp_path):
    code=secrets.token_urlsafe(24)
    config=AccessConfig(True,'https://private.example.test',mode='access-code',code_hash=digest(code),code_expires=time.time()+86400)
    app=create_app(tmp_path,worker_enabled=False,registry=[],access_config=config)
    with TestClient(app,base_url=config.origin) as client:yield app,client,config,code


def enter(client,config,code,**headers):
    nonce=client.get('/auth/config').json()['nonce']
    return client.post('/auth/access-code',json={'credential':code},headers={'Origin':config.origin,'X-CSRF-Token':nonce,**headers})


def test_real_code_session_and_logout(private):
    app,client,config,code=private
    public=client.get('/auth/config').json()
    assert public['mode']=='access-code' and not public['client_id']
    assert code not in str(public) and config.code_hash not in str(public)
    assert client.get('/api/status').status_code==401
    assert enter(client,config,code).status_code==200
    assert client.get('/api/status').status_code==200
    me=client.get('/auth/me').json();assert me['email']=='Private access'
    token=client.cookies.get(SESSION_COOKIE)
    assert client.post('/auth/logout',headers={'Origin':config.origin,'X-CSRF-Token':me['csrf']}).status_code==200
    client.cookies.set(SESSION_COOKIE,token)
    assert client.get('/api/status').status_code==401


def test_invalid_code_csrf_and_nonce_replay(private):
    app,client,config,code=private
    assert enter(client,config,'wrong').status_code==401
    assert enter(client,config,code,Origin='https://evil.test').status_code==403
    assert enter(client,config,code,**{'X-CSRF-Token':'wrong'}).status_code==403
    nonce=client.get('/auth/config').json()['nonce']
    headers={'Origin':config.origin,'X-CSRF-Token':nonce}
    assert client.post('/auth/access-code',json={'credential':code},headers=headers).status_code==200
    client.cookies.set(LOGIN_COOKIE,nonce)
    assert client.post('/auth/access-code',json={'credential':code},headers=headers).status_code==401


def test_expiry_and_rotation_revoke_sessions(private):
    app,client,config,code=private
    assert enter(client,config,code).status_code==200
    app.state.access.config=replace(config,code_expires=time.time()-1)
    assert client.get('/api/status').status_code==401
    assert enter(client,config,code).status_code==401
    app.state.access.config=replace(config,code_hash=digest(secrets.token_urlsafe(24)))
    assert client.get('/api/status').status_code==401
    assert enter(client,config,code).status_code==401


def test_code_mode_does_not_allow_google_or_unprotected_files(private):
    _,client,config,code=private
    assert client.post('/auth/google',json={'credential':code},headers={'Origin':config.origin}).status_code==404
    for path in ['/api/browse','/api/export','/app.js','/api/pois/1/image','/api/tiles/EMAP/16/54895/28092','/evidence/mobile-access/report.html']:
        assert client.get(path).status_code==401


@pytest.mark.parametrize('changes',[{'mode':'none'},{'code_hash':''},{'code_hash':'x'*64},{'code_expires':0},{'code_expires':time.time()+40*86400}])
def test_unsafe_code_configuration_refuses_start(private,changes):
    _,_,config,_=private
    with pytest.raises(ValueError):replace(config,**changes).validate()


def test_code_rate_limit(private):
    _,client,config,_=private
    for _ in range(20):assert enter(client,config,'wrong').status_code==401
    assert enter(client,config,'wrong').status_code==429
