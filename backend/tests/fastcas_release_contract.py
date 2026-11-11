"""Explicit CAS-enabled gate: installed wheel -> real routes -> SQLite.

Not collected by the local-mode suite, which intentionally has no optional SDK.
CI invokes this file by name; missing SDK/dependencies is an error, never a skip.
The loopback OIDC peer is disposable, not a deployed FastCAS integration claim.
"""
import base64
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from urllib.parse import parse_qs, urlencode, urlparse

from authlib.jose import JsonWebKey, jwt
from fastapi.testclient import TestClient

from app.web.api import create_web_app
from app.web.auth import create_user


def test_published_sdk_link_login_sid_logout_and_signed_revocation(tmp_path, monkeypatch):
    assert version('fastcas-sdk') == '0.1.2'
    key = JsonWebKey.generate_key('RSA', 2048, {'kid': 'fixture'}, is_private=True)
    peer = {'codes': {}, 'counter': 0, 'link': None}
    read_origin = 'http://127.0.0.1:8483'

    def sign(claims, typ='JWT'):
        return jwt.encode({'alg': 'RS256', 'kid': 'fixture', 'typ': typ},
                          {'iss': issuer, 'aud': 'read', 'sub': 'subject-a',
                           'iat': int(time.time()), 'exp': int(time.time()) + 120, **claims}, key).decode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, status=200):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_GET(self):
            path = urlparse(self.path).path
            if path == '/.well-known/openid-configuration':
                self.reply({'issuer': issuer, 'authorization_endpoint': issuer + '/authorize',
                            'token_endpoint': issuer + '/token', 'jwks_uri': issuer + '/jwks',
                            'userinfo_endpoint': issuer + '/userinfo'})
            elif path == '/jwks':
                self.reply({'keys': [key.as_dict(is_private=False)]})
            elif path == '/userinfo':
                self.reply({'sub': 'subject-a', 'email': 'local@example.org'})
            elif path == '/api/v1/account-links/resolve':
                self.reply(peer['link'])
            else:
                self.reply({'error': 'not_found'}, 404)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if self.path == '/token':
                form = parse_qs(raw.decode())
                grant = peer['codes'].pop(form.get('code', [''])[0], None)
                verifier = form.get('code_verifier', [''])[0]
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
                if not grant or challenge != grant['code_challenge'][0] or form.get('grant_type') != ['authorization_code']:
                    self.reply({'error': 'invalid_grant'}, 400)
                    return
                peer['counter'] += 1
                self.reply({'access_token': 'disposable-access', 'token_type': 'Bearer', 'expires_in': 120,
                            'id_token': sign({'nonce': grant['nonce'][0], 'sid': 'sid-' + str(peer['counter'])})})
            elif self.path == '/api/v1/link-intents':
                body = json.loads(raw)
                peer['local_ref'] = body['local_account_ref']
                self.reply({'id': 'intent-a', 'nonce': 'intent-nonce', 'client_id': 'read',
                            'local_account_ref': body['local_account_ref'], 'state': 'pending',
                            'expires_at': '2030-01-01T00:00:00Z'})
            elif self.path == '/api/v1/link-intents/intent-a/prepare':
                body = json.loads(raw)
                if body != {'nonce': 'intent-nonce', 'subject': 'subject-a'}:
                    self.reply({'error': 'invalid_intent'}, 400)
                    return
                peer['link'] = {'id': 'link-a', 'client_id': 'read', 'subject': 'subject-a',
                                'local_account_ref': peer['local_ref'], 'state': 'prepared',
                                'version': 1, 'verified_at': '2026-11-10T00:00:00Z'}
                self.reply(peer['link'])
            elif self.path == '/api/v1/link-intents/link-a/activate':
                peer['link'] = {**peer['link'], 'state': 'active', 'version': 2}
                self.reply(peer['link'])
            else:
                self.reply({'error': 'not_found'}, 404)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    issuer = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for suffix, value in {'ISSUER': issuer, 'CLIENT_ID': 'read', 'CLIENT_SECRET': 'disposable-secret',
                          'REDIRECT_URI': read_origin + '/api/auth/fastcas/callback',
                          'ALLOW_LOOPBACK_HTTP': 'true'}.items():
        monkeypatch.setenv('FASTREAD_FASTCAS_' + suffix, value)
    monkeypatch.setenv('FASTREAD_COOKIE_SECURE', 'false')
    monkeypatch.setenv('CHAT_VECTOR_INDEX_ENABLED', 'false')
    app = create_web_app(tmp_path)
    service = app.state.fastcas

    def finish(client, location):
        query = parse_qs(urlparse(location).query)
        code = 'code-' + str(len(peer['codes'])) + '-' + str(peer['counter'])
        peer['codes'][code] = query
        callback = '/api/auth/fastcas/callback?' + urlencode({'code': code, 'state': query['state'][0]})
        response = client.get(callback, follow_redirects=False)
        assert response.status_code == 302 and response.headers['location'].endswith('fastcas=complete')
        return callback

    def cas_login():
        client = TestClient(app, base_url=read_origin)
        response = client.get('/api/auth/fastcas/login', follow_redirects=False)
        assert response.status_code == 302
        callback = finish(client, response.headers['location'])
        assert client.get('/api/auth/me').status_code == 200
        assert client.get(callback, follow_redirects=False).headers['location'].endswith('fastcas=failed')
        return client

    try:
        user = create_user(app.state.store, 'local@example.org', 'original-password')
        local = TestClient(app, base_url=read_origin)
        preauth = local.get('/api/auth/session-init').json()['csrf']
        result = local.post('/api/auth/login', json={'email': user['email'], 'password': 'original-password'}, headers={'X-CSRF-Token': preauth})
        assert result.status_code == 200
        link = local.post('/api/auth/fastcas/link', json={'password': 'original-password'},
                          headers={'Origin': read_origin, 'X-CSRF-Token': result.json()['csrf']})
        assert link.status_code == 200
        finish(local, link.json()['url'])
        assert local.get('/api/auth/me').status_code == 200
        first, second = cas_login(), cas_login()
        notify = TestClient(app, base_url=read_origin)
        notice = {'jti': 'logout-one', 'sid': 'sid-2',
                  'events': {'http://schemas.openid.net/event/backchannel-logout': {}}}
        invalid = notify.post('/api/auth/fastcas/backchannel-logout', data={'logout_token': sign({**notice, 'aud': 'other'}, 'logout+jwt')})
        assert invalid.status_code == 401
        assert first.get('/api/auth/me').status_code == 200
        token = sign(notice, 'logout+jwt')
        for _ in range(2):
            assert notify.post('/api/auth/fastcas/backchannel-logout', data={'logout_token': token}).status_code == 200
        assert first.get('/api/auth/me').status_code == 401
        assert second.get('/api/auth/me').status_code == 200
        assert local.get('/api/auth/me').status_code == 200
        global_notice = {'jti': 'logout-all', 'events': notice['events']}
        assert notify.post('/api/auth/fastcas/backchannel-logout', data={'logout_token': sign(global_notice, 'logout+jwt')}).status_code == 200
        assert second.get('/api/auth/me').status_code == 401
        third = cas_login()
        revoked = {**peer['link'], 'state': 'revoked', 'version': 3}
        event = sign({'jti': 'revoke-one', 'event': {'type': 'account_link.revoked', 'link': revoked}}, 'fastcas-event+jwt')
        for _ in range(2):
            assert notify.post('/api/auth/fastcas/events', content=event, headers={'Content-Type': 'application/jwt'}).status_code == 200
        assert third.get('/api/auth/me').status_code == 401
        assert local.get('/api/auth/me').status_code == 200
        assert local.get('/api/auth/me').json()['workspace_id'] == user['workspace_id']
    finally:
        if service._sdk is not None:
            service.sdk.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
