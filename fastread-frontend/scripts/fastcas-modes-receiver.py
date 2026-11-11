"""Isolated browser fixture using the production app, auth and link store."""
import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
parser.add_argument('--port', required=True, type=int)
parser.add_argument('--frontend', required=True)
parser.add_argument('--link-state', choices=['none', 'prepared', 'active'], default='none')
args = parser.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
os.environ['FASTREAD_COOKIE_SECURE'] = 'false'
os.environ['CHAT_VECTOR_INDEX_ENABLED'] = 'false'

import uvicorn
from app.web.api import create_web_app
from app.web.auth import create_user

app = create_web_app(args.root, frontend=args.frontend)
user = create_user(app.state.store, 'reader@example.test', 'fixture-password-1234')
if args.link_state != 'none':
    app.state.fastcas.links.save({
        'id': 'browser-link', 'client_id': 'read', 'subject': 'browser-subject',
        'local_account_ref': user['user_id'], 'state': args.link_state,
        'version': 1, 'verified_at': '2026-11-11T00:00:00Z',
    })
print(f'FastRead source: {sys.modules[create_web_app.__module__].__file__}', flush=True)
uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
