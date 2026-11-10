"""Browser fixture: run the unchanged Read HTTP application with an isolated store."""
import argparse
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
parser.add_argument('--port', required=True, type=int)
parser.add_argument('--research', required=True)
args = parser.parse_args()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
os.environ['FASTREAD_COOKIE_SECURE'] = 'false'
os.environ['FASTRESEARCH_API_URL'] = args.research
os.environ['CHAT_VECTOR_INDEX_ENABLED'] = 'false'

import uvicorn
from app.web.api import create_web_app
from app.web.auth import create_user

app = create_web_app(args.root)
create_user(app.state.store, 'reader@example.test', 'fixture-password-1234')
uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
