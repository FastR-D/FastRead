import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.web.auth import create_user, login, token_hash
from app.web.fastcas_store import FastCASLinks, FastCASTransactions
from app.web.store import Store


def test_transaction_atomic_across_instances(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    FastCASTransactions(store).put({'state': 'once', 'expires_at': time.time()+300, 'verifier': 'private'})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: FastCASTransactions(Store(tmp_path)).take('once'), range(8)))
    assert sum(value is not None for value in results) == 1


def test_revocation_is_atomic_versioned_and_source_scoped(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    user = create_user(store, 'reader@example.com', 'original-password')
    local, _ = login(store, user['email'], 'original-password', 'test')
    links = FastCASLinks(store, 'https://cas.example.com', 'read')
    link = dict(id='old', client_id='read', subject='subject', local_account_ref=user['user_id'], state='prepared', version=1)
    links.save(link)
    links.save({**link, 'state': 'active', 'version': 2})
    with store.connect(write=True) as db:
        db.execute('''INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,cas_issuer,cas_link_id,cas_link_version)
            VALUES(?,?,?,?,?,'fastcas',?,?,?)''', ('cas-session', user['user_id'], user['workspace_id'], 'csrf', time.time()+300, links.issuer, 'old', 2))
    event = dict(id='event', type='account_link.revoked', link={**link, 'state': 'revoked', 'version': 3})
    # Fail after the mutation but before commit: both mapping and session survive.
    with store.connect(write=True) as db:
        db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON fastcas_events BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(Exception, match='injected'):
        links.apply_verified_event(event)
    assert store.one('SELECT state FROM fastcas_links')['state'] == 'active'
    assert store.one("SELECT token FROM sessions WHERE token='cas-session'")
    with store.connect(write=True) as db:
        db.execute('DROP TRIGGER fail_event')
    links.apply_verified_event(event)
    links.apply_verified_event(event)
    assert not store.one("SELECT token FROM sessions WHERE token='cas-session'")
    assert store.one('SELECT token FROM sessions WHERE token=?', (token_hash(local),))
    assert len(store.all('SELECT * FROM fastcas_events')) == 1
    links.save({**link, 'state': 'active', 'version': 2})
    assert store.one('SELECT state FROM fastcas_links')['state'] == 'revoked'
    links.save({**link, 'id': 'new', 'state': 'active', 'version': 2})
    links.apply_verified_event({**event, 'id': 'redelivery'})
    assert store.one("SELECT state FROM fastcas_links WHERE id='new'")['state'] == 'active'
    assert store.one('SELECT id FROM users WHERE id=?', (user['user_id'],))


def test_logout_is_atomic_sid_scoped_and_preserves_password_sessions(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    user = create_user(store, 'reader@example.com', 'original-password')
    local, _ = login(store, user['email'], 'original-password', 'test')
    links = FastCASLinks(store, 'https://cas.example.com', 'read')
    links.save(dict(id='link', client_id='read', subject='subject', local_account_ref=user['user_id'], state='active', version=2))
    with store.connect(write=True) as db:
        for token, sid in [('cas-a', 'sid-a'), ('cas-b', 'sid-b')]:
            db.execute('''INSERT INTO sessions(token,user_id,workspace_id,csrf,expires,auth_source,cas_issuer,cas_sid,cas_link_id,cas_link_version)
                VALUES(?,?,?,?,?,'fastcas',?,?,?,?)''', (token, user['user_id'], user['workspace_id'], 'csrf', time.time()+300, links.issuer, sid, 'link', 2))
        db.execute("CREATE TRIGGER fail_logout BEFORE INSERT ON fastcas_events BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(Exception, match='injected'):
        links.apply_verified_logout(dict(id='logout-a', subject='subject', sid='sid-a'))
    assert store.one("SELECT token FROM sessions WHERE token='cas-a'")
    with store.connect(write=True) as db:
        db.execute('DROP TRIGGER fail_logout')
    links.apply_verified_logout(dict(id='logout-a', subject='subject', sid='sid-a'))
    links.apply_verified_logout(dict(id='logout-a', subject='subject', sid='sid-a'))
    assert not store.one("SELECT token FROM sessions WHERE token='cas-a'")
    assert store.one("SELECT token FROM sessions WHERE token='cas-b'")
    links.apply_verified_logout(dict(id='logout-all', subject='subject', sid=None))
    assert not store.one("SELECT token FROM sessions WHERE token='cas-b'")
    assert store.one('SELECT token FROM sessions WHERE token=?', (token_hash(local),))
