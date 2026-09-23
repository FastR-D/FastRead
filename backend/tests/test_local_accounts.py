from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app.web.auth import login
from app.web.local_accounts import issue_credential, redeem_credential
from app.web.store import Store


def test_invite_single_use_and_recovery_preserves_workspace(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    token = issue_credential(store, 'invite', 'reader@example.com')
    def redeem():
        try:
            redeem_credential(store, 'invite', token, 'original-password')
            return True
        except HTTPException:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _: redeem(), range(4))) == 1
    before = store.one('SELECT * FROM users WHERE email=?', ('reader@example.com',))
    membership = store.one('SELECT * FROM memberships WHERE user_id=?', (before['id'],))
    login(store, before['email'], 'original-password', 'test')
    recovery = issue_credential(store, 'recovery', before['email'])
    redeem_credential(store, 'recovery', recovery, 'replacement-password')
    assert store.one('SELECT * FROM memberships WHERE user_id=?', (before['id'],)) == membership
    assert store.one('SELECT * FROM users WHERE email=?', (before['email'],))['id'] == before['id']
    assert not store.one('SELECT * FROM sessions WHERE user_id=?', (before['id'],))
    with pytest.raises(HTTPException):
        redeem_credential(store, 'recovery', recovery, 'another-password')
    login(store, before['email'], 'replacement-password', 'test')


def test_new_invite_invalidates_previous_token(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    old = issue_credential(store, 'invite', 'reader@example.com')
    new = issue_credential(store, 'invite', 'reader@example.com')
    with pytest.raises(HTTPException):
        redeem_credential(store, 'invite', old, 'original-password')
    redeem_credential(store, 'invite', new, 'original-password')


def test_http_login_registration_recovery_and_csrf(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.web.auth import token_hash
    from app.web.local_routes import register_local_routes

    monkeypatch.setenv('FASTREAD_COOKIE_SECURE', 'false')
    store = Store(tmp_path)
    store.initialize()
    app = FastAPI()
    register_local_routes(app, store, lambda response, token: response.set_cookie('fastread_session', token, httponly=True))
    client = TestClient(app)
    payload = {'email': 'reader@example.com', 'password': 'original-password'}
    assert client.post('/api/auth/login', json=payload).status_code == 403
    csrf = client.get('/api/auth/session-init').json()['csrf']
    client.headers['X-CSRF-Token'] = csrf
    invitation = issue_credential(store, 'invite', payload['email'])
    assert client.post('/api/auth/register', json={'token': invitation, 'password': payload['password']}).status_code == 200
    assert client.post('/api/auth/login', json=payload).status_code == 200
    old_session = client.cookies['fastread_session']
    recovery = issue_credential(store, 'recovery', payload['email'])
    assert client.post('/api/auth/recover', json={'token': recovery, 'password': 'replacement-password'}).status_code == 200
    assert not store.one('SELECT * FROM sessions WHERE token=?', (token_hash(old_session),))
    assert client.post('/api/auth/login', json=payload).status_code == 401
    payload['password'] = 'replacement-password'
    assert client.post('/api/auth/login', json=payload).status_code == 200
    # A token from a different browser cannot authorize login in this browser.
    another = TestClient(app)
    client.headers['X-CSRF-Token'] = another.get('/api/auth/session-init').json()['csrf']
    assert client.post('/api/auth/login', json=payload).status_code == 403


def test_http_failed_login_rate_limit(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.web.local_routes import register_local_routes

    monkeypatch.setenv('FASTREAD_COOKIE_SECURE', 'false')
    store = Store(tmp_path)
    store.initialize()
    app = FastAPI()
    register_local_routes(app, store, lambda *_: None)
    client = TestClient(app)
    client.headers['X-CSRF-Token'] = client.get('/api/auth/session-init').json()['csrf']
    for _ in range(8):
        assert client.post('/api/auth/login', json={'email': 'unknown@example.com', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'email': 'unknown@example.com', 'password': 'wrong'}).status_code == 429


def test_session_sources_and_research_login_preserve_local_session(tmp_path, monkeypatch):
    from app.web.auth import login_from_research, password_hash, token_hash
    store = Store(tmp_path)
    store.initialize()
    monkeypatch.setattr('app.web.auth.consume_research_ticket', lambda _: {'keyId': 'stable-key', 'person': 'Reader'})
    first, _ = login_from_research(store, 'ticket')
    user = store.one('SELECT * FROM users WHERE research_key_id=?', ('stable-key',))
    # Model a legacy account that already has a proven local credential.
    with store.connect(write=True) as db:
        db.execute('UPDATE users SET password=? WHERE id=?', (password_hash('original-password'), user['id']))
    local, _ = login(store, user['email'], 'original-password', 'test')
    assert store.one('SELECT auth_source FROM sessions WHERE token=?', (token_hash(local),))['auth_source'] == 'local'
    second, _ = login_from_research(store, 'new-ticket')
    assert not store.one('SELECT token FROM sessions WHERE token=?', (token_hash(first),))
    assert store.one('SELECT token FROM sessions WHERE token=?', (token_hash(local),))
    assert store.one('SELECT auth_source FROM sessions WHERE token=?', (token_hash(second),))['auth_source'] == 'research'
    store.initialize()
    assert store.one('SELECT token FROM sessions WHERE token=?', (token_hash(local),))


def test_research_account_can_add_local_credential_without_changing_identity(tmp_path, monkeypatch):
    from app.web.auth import login_from_research, token_hash
    from app.web.local_accounts import set_local_credential
    store = Store(tmp_path)
    store.initialize()
    monkeypatch.setattr('app.web.auth.consume_research_ticket', lambda _: {'keyId': 'key', 'person': 'Reader'})
    research, _ = login_from_research(store, 'fresh-ticket')
    before = store.one('SELECT * FROM users')
    workspace = store.one('SELECT * FROM memberships')
    set_local_credential(store, research, 'reader@example.com', 'new-local-password', '')
    after = store.one('SELECT * FROM users')
    assert after['id'] == before['id'] and after['research_key_id'] == 'key'
    assert store.one('SELECT * FROM memberships') == workspace
    local, _ = login(store, 'reader@example.com', 'new-local-password', 'peer')
    login_from_research(store, 'another-ticket')
    assert store.one('SELECT email FROM users')['email'] == 'reader@example.com'
    assert store.one('SELECT token FROM sessions WHERE token=?', (token_hash(local),))
    with pytest.raises(HTTPException):
        set_local_credential(store, local, 'reader@example.com', 'changed-password', 'wrong')


def test_stale_research_session_cannot_set_local_credential(tmp_path, monkeypatch):
    from app.web.auth import login_from_research
    from app.web.local_accounts import set_local_credential
    store = Store(tmp_path)
    store.initialize()
    monkeypatch.setattr('app.web.auth.consume_research_ticket', lambda _: {'keyId': 'key', 'person': 'Reader'})
    research, _ = login_from_research(store, 'ticket')
    with store.connect(write=True) as db:
        db.execute('UPDATE sessions SET authenticated_at=0')
    with pytest.raises(HTTPException) as error:
        set_local_credential(store, research, 'reader@example.com', 'new-local-password', '')
    assert error.value.status_code == 403
    assert store.one('SELECT password FROM users')['password'] == 'disabled'
