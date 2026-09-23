"""Real FastCAS OIDC provider against FastRead's actual auth route composition."""
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlparse, parse_qs

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.auth import create_user, require_user
from app.web.fastcas_routes import register_fastcas_routes
from app.web.local_routes import register_local_routes
from app.web.store import Store

issuer = os.environ['FASTCAS_CONTRACT_ISSUER']
origin = 'http://127.0.0.1:18080'
backchannel = urlparse(os.environ['FASTCAS_CONTRACT_BACKCHANNEL'])
os.environ.update(FASTREAD_FASTCAS_ISSUER=issuer, FASTREAD_FASTCAS_CLIENT_ID='read', FASTREAD_FASTCAS_CLIENT_SECRET='integration-client-secret-32-characters-long', FASTREAD_FASTCAS_REDIRECT_URI=origin+'/api/auth/fastcas/callback', FASTREAD_FASTCAS_ALLOW_LOOPBACK_HTTP='true', FASTREAD_COOKIE_SECURE='false')

with tempfile.TemporaryDirectory() as temp, httpx.Client(follow_redirects=False) as browser:
    store = Store(temp)
    store.initialize()
    user = create_user(store, 'alice@example.test', 'local-original-password')
    paper = store.intake_fastnews(user['workspace_id'], {'title': 'Original paper', 'url': 'https://example.com/paper', 'authors': '', 'abstract': '', 'venue': '', 'year': '', 'external_id': 'original'})
    app = FastAPI()
    app.state.store = store
    def set_cookie(response, token):
        response.set_cookie('fastread_session', token, httponly=True, samesite='lax', path='/')
    register_local_routes(app, store, set_cookie)
    register_fastcas_routes(app, store, set_cookie)
    client = TestClient(app, base_url=origin, follow_redirects=False)
    class LogoutReceiver(BaseHTTPRequestHandler):
        def do_POST(self):
            size = int(self.headers.get('Content-Length', '0'))
            payload = self.rfile.read(size)
            response = client.post(self.path, content=payload, headers={'Content-Type': self.headers.get('Content-Type', '')})
            self.send_response(response.status_code)
            self.send_header('Content-Length', '0')
            self.end_headers()
        def log_message(self, *_):
            pass
    receiver = ThreadingHTTPServer((backchannel.hostname, backchannel.port), LogoutReceiver)
    receiver_thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    receiver_thread.start()
    client.headers['Origin'] = origin
    client.headers['X-CSRF-Token'] = client.get('/api/auth/session-init').json()['csrf']
    response = client.post('/api/auth/login', json={'email': user['email'], 'password': 'local-original-password'})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf']
    local_csrf = response.json()['csrf']
    local_cookie = client.cookies['fastread_session']

    def complete(url):
        response = browser.get(url)
        assert response.status_code == 302, response.text
        login_url = urljoin(issuer, response.headers['location'])
        request_id = parse_qs(urlparse(login_url).query)['auth_request_id'][0]
        body = browser.get(login_url).text
        if 'name="password"' in body:
            csrf = re.search(r'name="csrf" value="([^"]+)"', body)[1]
            response = browser.post(issuer+'/login', data=dict(csrf=csrf, auth_request_id=request_id, email='alice@example.test', password='correct horse battery staple', action='login'), headers={'Origin': issuer})
            assert response.status_code == 303, response.text
            body = browser.get(urljoin(issuer, response.headers['location'])).text
        csrf = re.search(r'name="csrf" value="([^"]+)"', body)[1]
        response = browser.post(issuer+'/login', data=dict(csrf=csrf, auth_request_id=request_id, action='approve'), headers={'Origin': issuer})
        assert response.status_code == 303, response.text
        response = browser.get(urljoin(issuer, response.headers['location']))
        assert response.status_code == 302, response.text
        return response.headers['location']

    # Same email alone must not log into the pre-existing local user.
    start = client.get('/api/auth/fastcas/login')
    assert start.status_code == 302, (start.status_code, start.text)
    response = client.get(complete(start.headers['location']))
    assert response.headers['location'] == '/?fastcas=failed'
    assert client.cookies['fastread_session'] == local_cookie
    assert len(store.all('SELECT * FROM users')) == 1
    response = client.post('/api/auth/fastcas/link', json={'password': 'local-original-password'})
    assert response.status_code == 200, response.text
    response = client.get(complete(response.json()['url']))
    assert response.headers['location'] == '/?fastcas=complete', response.text
    assert client.cookies['fastread_session'] == local_cookie
    assert client.get('/api/auth/fastcas/status').json()['link']['state'] == 'active'
    response = client.get('/api/auth/fastcas/login')
    callback = complete(response.headers['location'])
    response = client.get(callback)
    assert response.headers['location'] == '/?fastcas=complete'
    cas_cookie = client.cookies['fastread_session']
    assert cas_cookie != local_cookie
    session = app.state.fastcas.session(cas_cookie)
    assert session['user_id'] == user['user_id'] and session['workspace_id'] == user['workspace_id']
    assert session['auth_source'] == 'fastcas'
    assert store.one('SELECT workspace_id FROM papers WHERE id=?', (paper['id'],))['workspace_id'] == user['workspace_id']
    assert client.get(callback).headers['location'] == '/?fastcas=failed'
    if signal := os.environ.get('FASTCAS_CONTRACT_STATUS_SIGNAL'):
        Path(signal).write_text('ready')
        deadline = time.monotonic()+8
        while time.monotonic()<deadline and app.state.fastcas.session(cas_cookie):
            time.sleep(.05)
        assert not app.state.fastcas.session(cas_cookie)
        assert app.state.fastcas.session(local_cookie)
        assert store.one('SELECT workspace_id FROM papers WHERE id=?', (paper['id'],))['workspace_id'] == user['workspace_id']
        print('FastRead identity status contract passed: signed event revoked CAS session, local session preserved')
        app.state.fastcas.sdk.close()
        receiver.shutdown(); receiver.server_close(); receiver_thread.join(timeout=5)
        raise SystemExit(0)
    csrf = browser.get(issuer+'/api/v1/me').json()['csrf']
    signed_out = browser.post(issuer+'/api/v1/me/logout-all', json={}, headers={'Origin':issuer,'X-CSRF-Token':csrf})
    assert signed_out.status_code == 204, signed_out.text
    deadline = time.monotonic()+5
    while time.monotonic()<deadline and app.state.fastcas.session(cas_cookie):
        time.sleep(.05)
    assert not app.state.fastcas.session(cas_cookie)
    assert app.state.fastcas.session(local_cookie)
    client.cookies.set('fastread_session', local_cookie, domain='127.0.0.1', path='/')
    client.headers['X-CSRF-Token'] = local_csrf
    assert client.post('/api/auth/fastcas/revoke', json={'password': 'local-original-password'}).status_code == 200
    assert app.state.fastcas.session(local_cookie)
    assert not app.state.fastcas.session(cas_cookie)
    assert len(store.all('SELECT * FROM users')) == 1
    app.state.fastcas.sdk.close()
    receiver.shutdown()
    receiver.server_close()
    receiver_thread.join(timeout=5)
print('FastRead real-provider contract passed: local account, no email merge, bind, login, replay, signed global logout, revoke, workspace preservation')
