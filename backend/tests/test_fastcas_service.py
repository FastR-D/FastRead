import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.web.auth import create_user, login, require_user, token_hash
from app.web.fastcas_service import FastCASService
from app.web.fastcas_routes import register_fastcas_routes
from app.web.store import Store


class Provider:
    config = SimpleNamespace(issuer='https://cas.example.com', client_id='read', redirect_uri='https://read.example.com/api/auth/fastcas/callback')
    calls = 0
    def resolve_link(self, subject):
        self.calls += 1
        assert subject == self.link['subject']
        return self.link.copy()
    def revoke_link(self, link):
        self.link = {**link, 'state': 'revoked', 'version': link['version']+1}
        return self.link.copy()
    def get_link(self, link_id):
        assert link_id == self.link['id']
        return self.link.copy()
    def activate_link(self, link_id):
        assert link_id == self.link['id']
        self.link = {**self.link, 'state': 'active', 'version': self.link['version']+1}
        return self.link.copy()


def setup(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    user = create_user(store, 'local@example.com', 'original-password')
    provider = Provider()
    provider.link = dict(id='link', client_id='read', subject='cas-subject', local_account_ref=user['user_id'], state='active', version=2)
    service = FastCASService(store, provider)
    service.links.save(provider.link)
    identity = dict(issuer=provider.config.issuer, subject='cas-subject', sid='cas-session')
    return store, user, provider, service, identity


def test_login_preserves_account_acl_and_revoke_keeps_local_session(tmp_path):
    store, user, provider, service, identity = setup(tmp_path)
    local, _ = login(store, user['email'], 'original-password', 'peer')
    cas = service._login(provider.link, identity)
    session = service.session(cas)
    assert session['user_id'] == user['user_id']
    assert session['workspace_id'] == user['workspace_id']
    assert session['auth_source'] == 'fastcas'
    service.validate_session(session)
    assert provider.calls == 0
    service.validate_session({**session, 'cas_checked': 0})
    assert provider.calls == 1
    service.revoke(local, 'original-password', 'peer')
    assert service.session(local)
    assert not service.session(cas)
    with pytest.raises(HTTPException):
        service._login(provider.link, identity)
    assert store.one('SELECT role FROM memberships WHERE user_id=?', (user['user_id'],))['role'] == 'owner'


def test_binding_conflict_and_pending_recovery(tmp_path):
    store, user, provider, service, identity = setup(tmp_path)
    with pytest.raises(HTTPException):
        service._login({**provider.link, 'local_account_ref': 'other-user'}, identity)
    with store.connect(write=True) as db:
        db.execute('DELETE FROM fastcas_links')
    provider.link = {**provider.link, 'state': 'prepared', 'version': 1}
    service.links.save(provider.link)
    service.reconcile(service.current(user['user_id']))
    assert service.current(user['user_id'])['state'] == 'active'
    service._login(provider.link, identity)


def test_expired_confirmation_and_disabled_provider_only_affect_cas(tmp_path):
    store, user, provider, service, identity = setup(tmp_path)
    session = service.session(service._login(provider.link, identity))
    provider.link['state'] = 'revoked'
    with pytest.raises(HTTPException):
        service.validate_session({**session, 'cas_checked': 0})
    service.enabled = False
    with pytest.raises(HTTPException):
        service.validate_session(session)
    assert login(store, user['email'], 'original-password', 'peer')


def test_http_optional_mode_and_mutation_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv('FASTREAD_COOKIE_SECURE', 'false')
    store, user, provider, service, identity = setup(tmp_path)
    app = FastAPI()
    app.state.store = store
    register_fastcas_routes(app, store, lambda *_: None, service)
    client = TestClient(app, base_url='https://read.example.com')
    assert client.get('/api/auth/fastcas/status').status_code == 401
    local, csrf = login(store, user['email'], 'original-password', 'peer')
    client.cookies.set('fastread_session', local)
    client.headers['X-CSRF-Token'] = csrf
    assert client.get('/api/auth/fastcas/status').json()['link']['state'] == 'active'
    assert client.post('/api/auth/fastcas/revoke', json={'password': 'original-password'}).status_code == 403
    client.headers['Origin'] = 'https://read.example.com'
    assert client.post('/api/auth/fastcas/revoke', json={'password': 'wrong'}).status_code == 403
    assert client.post('/api/auth/fastcas/revoke', json={'password': 'original-password'}).status_code == 200
    assert service.session(local)
    assert client.post('/api/auth/fastcas/events', json={}).status_code == 415
    service.enabled = False
    assert client.get('/api/auth/fastcas/available').json() == {'enabled': False}
    assert client.get('/api/auth/fastcas/login').status_code == 404
    assert client.get('/api/auth/fastcas/status').json()['enabled'] is False


def test_unconfigured_service_does_not_import_sdk(tmp_path, monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'fastcas':
            raise AssertionError('Disabled provider imported SDK')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    for key in ('ISSUER','CLIENT_ID','CLIENT_SECRET','REDIRECT_URI'):
        monkeypatch.delenv('FASTREAD_FASTCAS_'+key, raising=False)
    store = Store(tmp_path)
    store.initialize()
    service = FastCASService(store)
    assert not service.enabled
    with pytest.raises(HTTPException) as failure:
        _ = service.sdk
    assert failure.value.status_code == 404


def test_revoke_recovers_lost_response_and_reconcile_rejects_stale_activation(tmp_path):
    store, user, provider, service, identity = setup(tmp_path)
    local, _ = login(store, user['email'], 'original-password', 'peer')
    cas = service._login(provider.link, identity)
    # Simulate remote revoke committed but its HTTP response never arrived.
    provider.revoke_link(provider.link)
    assert service.current(user['user_id'])['state'] == 'active'
    service.revoke(local, 'original-password', 'peer')
    assert not service.session(cas)
    assert service.session(local)
    with pytest.raises(HTTPException) as error:
        service._accept_remote({**provider.link, 'state': 'active', 'version': 2})
    assert error.value.status_code == 409
    assert service.current(user['user_id']) is None


def test_reconcile_remote_revocation_deletes_only_cas_sessions(tmp_path):
    store, user, provider, service, identity = setup(tmp_path)
    local, _ = login(store, user['email'], 'original-password', 'peer')
    cas = service._login(provider.link, identity)
    provider.revoke_link(provider.link)
    assert service.reconcile(service.current(user['user_id']))['state'] == 'revoked'
    assert not service.session(cas)
    assert service.session(local)
