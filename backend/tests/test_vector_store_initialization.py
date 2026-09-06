import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest

from app.services import vector_store


def configure(monkeypatch, tmp_path, factory):
    monkeypatch.setattr(vector_store, 'VECTOR_DB_DIR', tmp_path / 'vectors')
    monkeypatch.setattr(vector_store, '_CLIENTS', {})
    monkeypatch.setitem(sys.modules, 'chromadb', SimpleNamespace(PersistentClient=factory))
    monkeypatch.setitem(sys.modules, 'chromadb.config', SimpleNamespace(Settings=lambda **kwargs: kwargs))


def test_concurrent_managers_share_one_initialized_client(monkeypatch, tmp_path):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return object()

    configure(monkeypatch, tmp_path, factory)
    ready = Barrier(8)

    def create(_):
        ready.wait()
        return vector_store.VectorStoreManager()._client

    with ThreadPoolExecutor(max_workers=8) as pool:
        clients = list(pool.map(create, range(8)))

    assert len(calls) == 1
    assert all(client is clients[0] for client in clients)


def test_failed_client_is_not_cached(monkeypatch, tmp_path):
    calls = []
    client = object()

    def factory(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError('startup failed')
        return client

    configure(monkeypatch, tmp_path, factory)
    with pytest.raises(RuntimeError, match='startup failed'):
        vector_store.VectorStoreManager()
    assert vector_store.VectorStoreManager()._client is client
    assert len(calls) == 2
