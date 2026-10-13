import pytest
from fastapi import HTTPException
from app.web import auth
from app.web.store import Store
from app.web.api import ImportInput


def test_import_preserves_production_metadata():
    value = ImportInput(url='https://example.com/paper.pdf', authors='Alice; Bob', title='Paper')
    assert value.authors == ['Alice', 'Bob']
    assert value.title == 'Paper'


def test_rotated_research_key_keeps_existing_workspace(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.initialize()
    identity = {'keyId': 'old-key', 'person': 'Reader', 'accountId': 'stable-account'}
    monkeypatch.setattr(auth, 'consume_research_ticket', lambda _: identity)
    auth.login_from_research(store, 'first')
    before = store.one('SELECT * FROM memberships')
    identity['keyId'] = 'new-key'
    auth.login_from_research(store, 'second')
    assert store.one('SELECT * FROM memberships') == before
    assert len(store.all('SELECT * FROM users')) == 1
    assert store.one('SELECT research_account_id FROM users')['research_account_id'] == 'stable-account'


def test_cannot_rebind_key_to_other_account(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.initialize()
    identity = {'keyId': 'same-key', 'person': 'Reader', 'accountId': 'account-a'}
    monkeypatch.setattr(auth, 'consume_research_ticket', lambda _: identity)
    auth.login_from_research(store, 'first')
    identity['accountId'] = 'account-b'
    with pytest.raises(HTTPException) as error:
        auth.login_from_research(store, 'second')
    assert error.value.status_code == 409
