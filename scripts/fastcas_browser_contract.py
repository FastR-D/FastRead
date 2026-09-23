"""Real Chrome -> FastRead web -> FastCAS/PostgreSQL browser contract."""
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import uvicorn

issuer = os.environ['FASTCAS_CONTRACT_ISSUER']
origin = os.environ['FASTCAS_CONTRACT_READ_ORIGIN']
port = urlparse(origin).port
root = Path(__file__).resolve().parents[1]
frontend = root / 'fastread-frontend' / 'dist'
os.environ.update(
    FASTREAD_FASTCAS_ISSUER=issuer,
    FASTREAD_FASTCAS_CLIENT_ID='read',
    FASTREAD_FASTCAS_CLIENT_SECRET='integration-client-secret-32-characters-long',
    FASTREAD_FASTCAS_REDIRECT_URI=origin + '/api/auth/fastcas/callback',
    FASTREAD_FASTCAS_ALLOW_LOOPBACK_HTTP='true',
    FASTREAD_COOKIE_SECURE='false',
    FASTREAD_PUBLIC_ORIGIN=origin,
)

from app.web.api import create_web_app  # noqa: E402
from app.web.auth import create_user  # noqa: E402
from app.web.store import Store  # noqa: E402

with tempfile.TemporaryDirectory() as temp:
    store = Store(temp)
    store.initialize()
    user = create_user(store, 'alice@example.test', 'local-original-password')
    store.intake_fastnews(user['workspace_id'], {
        'title': 'Browser preserved paper', 'url': 'https://example.com/paper',
        'authors': '', 'abstract': '', 'venue': '', 'year': '',
        'external_id': 'browser-original',
    })
    app = create_web_app(temp, frontend=frontend)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error', lifespan='off'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if httpx.get(origin + '/api/auth/fastcas/available', timeout=.5).status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(.05)
        else:
            raise AssertionError('FastRead browser server startup timeout')
        subprocess.run(
            ['node', str(root.parent / 'FastCAS' / 'web' / 'tests' / 'fastread_contract.mjs')],
            env={**os.environ, 'FASTCAS_CONTRACT_READ_ORIGIN': origin},
            check=True, timeout=70,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        app.state.fastcas.sdk.close()
