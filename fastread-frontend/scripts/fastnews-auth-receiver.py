"""Production Read + published SDK; disposable HTTP OIDC/Research peers."""
import argparse
import base64
import hashlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
parser.add_argument('--port', type=int, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'backend'))
from authlib.jose import JsonWebKey, jwt
import uvicorn
from app.web.api import create_web_app
from app.web.auth import create_user

assert version('fastcas-sdk') == '0.1.2'
key = JsonWebKey.generate_key('RSA', 2048, {'kid': 'browser'}, is_private=True)
codes = {}
link = None
origin = f'http://127.0.0.1:{args.port}'

class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, value, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(value).encode())

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/.well-known/openid-configuration':
            self.reply(dict(issuer=issuer, authorization_endpoint=issuer+'/authorize', token_endpoint=issuer+'/token',
                            jwks_uri=issuer+'/jwks', userinfo_endpoint=issuer+'/userinfo'))
        elif url.path == '/jwks':
            self.reply({'keys': [key.as_dict(is_private=False)]})
        elif url.path == '/userinfo':
            self.reply({'sub': 'browser-subject', 'email': 'cas@example.test'})
        elif url.path == '/api/v1/account-links/resolve':
            self.reply(link)
        elif url.path == '/authorize':
            params = parse_qs(url.query)
            code = str(time.time_ns())
            codes[code] = params
            self.send_response(302)
            self.send_header('Location', params['redirect_uri'][0]+'?'+urlencode({'code': code, 'state': params['state'][0]}))
            self.end_headers()
        else:
            self.reply({'error': 'not_found'}, 404)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path == '/api/sso/consume':
            body = json.loads(raw)
            assert body['audience'] == 'fast-read'
            if body['ticket'] == 'valid-research':
                self.reply({'keyId': 'research-reader', 'person': 'Research reader'})
            else:
                self.reply({'error': 'Expired ticket'}, 401)
        elif self.path == '/token':
            form = parse_qs(raw.decode())
            grant = codes.pop(form['code'][0])
            challenge = base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'][0].encode()).digest()).rstrip(b'=').decode()
            assert challenge == grant['code_challenge'][0]
            assert form['redirect_uri'] == grant['redirect_uri']
            assert form['grant_type'] == ['authorization_code']
            now = int(time.time())
            token = jwt.encode({'alg': 'RS256', 'kid': 'browser', 'typ': 'JWT'},
                               {'iss': issuer, 'aud': 'read', 'sub': 'browser-subject', 'iat': now, 'exp': now+120,
                                'nonce': grant['nonce'][0], 'sid': 'browser-sid'}, key).decode()
            self.reply({'access_token': 'disposable', 'token_type': 'Bearer', 'expires_in': 120, 'id_token': token})
        else:
            self.reply({'error': 'not_found'}, 404)

provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
issuer = f'http://127.0.0.1:{provider.server_port}'
threading.Thread(target=provider.serve_forever, daemon=True).start()
for name in list(os.environ):
    if name.startswith('FASTREAD_FASTCAS_'):
        del os.environ[name]
os.environ.update(FASTREAD_FASTCAS_ISSUER=issuer, FASTREAD_FASTCAS_CLIENT_ID='read',
                  FASTREAD_FASTCAS_CLIENT_SECRET='disposable-secret', FASTREAD_FASTCAS_REDIRECT_URI=origin+'/api/auth/fastcas/callback',
                  FASTREAD_FASTCAS_ALLOW_LOOPBACK_HTTP='true', FASTREAD_COOKIE_SECURE='false',
                  CHAT_VECTOR_INDEX_ENABLED='false', FASTRESEARCH_API_URL=issuer)
app = create_web_app(args.root, frontend=repo / 'fastread-frontend/dist')
user = create_user(app.state.store, 'cas@example.test', 'fixture-password-1234')
create_user(app.state.store, 'old@example.test', 'fixture-password-1234')
link = dict(id='browser-link', client_id='read', local_account_ref=user['user_id'], subject='browser-subject', state='active', version=1)
app.state.fastcas.links.save(link)
print(f'SDK {version("fastcas-sdk")}; source {sys.modules[create_web_app.__module__].__file__}', flush=True)
uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
