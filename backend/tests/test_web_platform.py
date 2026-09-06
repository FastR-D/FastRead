import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.web.api import create_web_app
from app.web.auth import create_user
from app.web.store import Store
from app.web.worker import execute


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTREAD_COOKIE_SECURE", "false")
    monkeypatch.setenv("CHAT_VECTOR_INDEX_ENABLED", "false")
    app = create_web_app(tmp_path)
    store = app.state.store
    a = create_user(store, "a@example.org", "test-password-for-a")
    b = create_user(store, "b@example.org", "test-password-for-b")
    clients = []
    for email, password in [("a@example.org", "test-password-for-a"), ("b@example.org", "test-password-for-b")]:
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        clients.append(client)
    return store, a, b, *clients


def document(text="A real page of scientific evidence about a controlled experiment."):
    return {"title": "Controlled evidence", "doi": "10.1234/test", "pages": [{"page": 1, "text": text}], "page_count": 1}


def test_web_auth_is_not_loopback_trust(setup):
    store, a, b, ca, cb = setup
    anonymous = TestClient(ca.app, client=("127.0.0.1", 1234))
    for endpoint in ["/api/papers", "/api/jobs", "/api/providers"]:
        assert anonymous.get(endpoint).status_code == 401
    assert anonymous.get("/api/tasks").status_code == 404
    assert anonymous.get("/uploads/private.pdf").status_code == 404
    assert ca.post("/api/imports/url", json={"url": "https://arxiv.org/pdf/1234.56789"}, headers={"X-CSRF-Token": "wrong", "Idempotency-Key": "one"}).status_code == 403
    assert ca.post("/api/imports/url", json={"url": "https://arxiv.org/pdf/1234.56789"}, headers={"Origin": "https://attacker.example", "Idempotency-Key": "one"}).status_code == 403


def test_metadata_model_import_checks_ownership_quota_and_idempotency(setup):
    store, a, b, ca, cb = setup
    old = store.enqueue(a["workspace_id"], a["user_id"], "import_url", {"url": "https://example.org/legacy.pdf"}, "legacy-url")
    replay = ca.post("/api/imports/url", json={"url": "https://example.org/legacy.pdf"}, headers={"Idempotency-Key": "legacy-url"})
    assert replay.status_code == 202 and replay.json()["id"] == old["id"]
    with store.connect(write=True) as db:
        db.execute("INSERT INTO providers VALUES(?,?,?,?,?,?,?)", ("metadata-provider", a["workspace_id"], "Fixture", "https://example.org/v1", "unused", json.dumps(["qwen-fixture-27b"]), time.time()))
    payload = {"url": "https://arxiv.org/pdf/1234.56789", "provider_id": "metadata-provider", "model": "qwen-fixture-27b"}
    headers = {"Idempotency-Key": "metadata-import"}
    assert cb.post("/api/imports/url", json=payload, headers=headers).status_code == 400
    first = ca.post("/api/imports/url", json=payload, headers=headers)
    assert first.status_code == 202
    assert ca.post("/api/imports/url", json=payload, headers=headers).json()["id"] == first.json()["id"]
    assert store.one("SELECT billable FROM jobs WHERE id=?", (first.json()["id"],))["billable"] == 1
    file = {"file": ("fixture.pdf", b"%PDF-fixture", "application/pdf")}
    data = {"provider_id": "metadata-provider", "model": "qwen-fixture-27b"}
    assert cb.post("/api/imports/pdf", files=file, data=data, headers={"Idempotency-Key": "pdf-model"}).status_code == 400
    assert ca.post("/api/imports/pdf", files=file, data={"provider_id": "metadata-provider"}, headers={"Idempotency-Key": "incomplete"}).status_code == 400
    uploaded = ca.post("/api/imports/pdf", files=file, data=data, headers={"Idempotency-Key": "pdf-model"})
    assert uploaded.status_code == 202
    assert ca.post("/api/imports/pdf", files=file, headers={"Idempotency-Key": "pdf-model"}).status_code == 409
    with store.connect(write=True) as db:
        db.execute("UPDATE workspaces SET daily_limit=2 WHERE id=?", (a["workspace_id"],))
    assert ca.post("/api/imports/url", json=payload, headers={"Idempotency-Key": "over-quota"}).status_code == 429


def test_same_pdf_metadata_upgrade_is_versioned_and_cannot_downgrade(setup):
    store, a, _, _, _ = setup
    raw = document() | {"metadata_resolution": {"status": "layout_only"}}
    first = store.ingest(a["workspace_id"], raw)
    verified = raw | {"year": 2020, "metadata_resolution": {"status": "registry_verified", "retrieved_at": "first"}}
    second = store.ingest(a["workspace_id"], verified)
    assert second["paper_id"] == first["paper_id"] and second["version_id"] != first["version_id"]
    assert store.ingest(a["workspace_id"], raw)["version_id"] == second["version_id"]
    verified["metadata_resolution"]["retrieved_at"] = "later"
    assert store.ingest(a["workspace_id"], verified)["deduplicated"] is True
    assert store.document(a["workspace_id"], first["paper_id"])[2]["year"] == 2020


@pytest.mark.parametrize("model_fails", [False, True])
def test_worker_import_dispatches_metadata_model_and_persists_fallback(setup, monkeypatch, model_fails):
    from types import SimpleNamespace
    store, a, _, _, _ = setup
    raw = {"fetch_status": "pdf_ok", "source_type": "pdf", "text": "A complete scientific title\nAlice Smith",
           "first_page_layout": {"title_candidates": [{"text": "A complete scientific title", "blocks": ["p1:l0"]}],
            "blocks": [{"id": "p1:l0", "text": "A complete scientific title"}, {"id": "p1:l1", "text": "Alice Smith"}]}}
    monkeypatch.setattr("app.services.paper_ingest_service.fetch_source_snapshot", lambda *a, **kw: raw)
    with store.connect(write=True) as db:
        db.execute("INSERT INTO providers VALUES(?,?,?,?,?,?,?)", ("fixture", a["workspace_id"], "Fixture", "https://example.org/v1", "unused", '["qwen-fixture-27b"]', time.time()))
    monkeypatch.setattr("app.services.secret_store.unprotect_secret", lambda _: "disposable-fixture-value")
    closed = []
    monkeypatch.setattr("openai.OpenAI", lambda **kw: SimpleNamespace(close=lambda: closed.append(True)))
    def respond(*args, **kwargs):
        if model_fails:
            raise TimeoutError()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "title": {"text": "A complete scientific title", "blocks": ["p1:l0"]},
            "authors": [{"text": "Alice Smith", "blocks": ["p1:l1"]}], "year": None})))])
    monkeypatch.setattr("app.services.llm_compat.create_chat_completion", respond)
    job = store.enqueue(a["workspace_id"], a["user_id"], "import_url",
        {"url": "https://example.org/paper.pdf", "provider_id": "fixture", "model": "qwen-fixture-27b"}, "worker-import", billable=True)
    claimed = store.claim("metadata-worker")
    execute(store, claimed, "metadata-worker")
    saved = store.one("SELECT * FROM jobs WHERE id=?", (job["id"],))
    assert saved["state"] == "succeeded" and saved["dispatch_started"] == 1 and closed
    result = json.loads(saved["result"])
    paper = store.document(a["workspace_id"], result["paper_id"])[2]
    assert paper["metadata_resolution"]["model_status"] == ("failed_or_rejected" if model_fails else "source_located")
    assert paper["authors"] == ([] if model_fails else ["Alice Smith"])


def test_workspace_ownership_every_resource(setup):
    store, a, b, ca, cb = setup
    imported = store.ingest(a["workspace_id"], document())
    pid = imported["paper_id"]
    assert ca.get(f"/api/papers/{pid}").status_code == 200
    assert cb.get("/api/papers").json()["items"] == []
    cid = ca.post(f"/api/papers/{pid}/conversations").json()["id"]
    for path in [f"/papers/{pid}", f"/papers/{pid}/pages/1", f"/papers/{pid}/file", f"/papers/{pid}/reports", f"/papers/{pid}/export", f"/conversations/{cid}/messages"]:
        assert cb.get("/api" + path).status_code == 404, path
    assert cb.put(f"/api/papers/{pid}/summary", json={"content": "overwrite"}).status_code == 404
    assert cb.post(f"/api/papers/{pid}/index", headers={"Idempotency-Key": "x"}).status_code == 404
    assert cb.post(f"/api/papers/{pid}/conversations").status_code == 404
    job = ca.post(f"/api/papers/{pid}/index", headers={"Idempotency-Key": "index"}).json()
    assert cb.get(f"/api/jobs/{job['id']}").status_code == 404


def test_paginated_summaries_and_immutable_versions(setup):
    store, a, _, ca, _ = setup
    first = store.ingest(a["workspace_id"], document())
    duplicate = store.ingest(a["workspace_id"], document())
    assert duplicate == first | {"deduplicated": True}
    second = store.ingest(a["workspace_id"], document("New corrected document version with different page evidence."))
    assert first["paper_id"] == second["paper_id"]
    assert first["version_id"] != second["version_id"]
    page = ca.get(f"/api/papers/{first['paper_id']}/pages/1?version={first['version_id']}").json()
    assert page["text"] == document()["pages"][0]["text"]
    listing = ca.get("/api/papers?limit=1").json()
    assert listing["total"] == 1 and len(listing["items"]) == 1
    for forbidden in ["pages", "paperDocument", "result", "metadata", "text"]:
        assert forbidden not in listing["items"][0]


def test_atomic_dedupe_and_concurrency_limits(setup):
    store, a, b, _, _ = setup
    def submit(_):
        return store.enqueue(a["workspace_id"], a["user_id"], "index", {}, "same")["id"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(submit, range(8)))
    assert len(set(ids)) == 1
    with pytest.raises(ValueError, match="conflict"):
        store.enqueue(a["workspace_id"], a["user_id"], "index", {"changed": True}, "same")
    store.enqueue(a["workspace_id"], a["user_id"], "index", {}, "second")
    store.enqueue(b["workspace_id"], b["user_id"], "index", {}, "third")
    with ThreadPoolExecutor(max_workers=8) as pool:
        claimed = [j for j in pool.map(lambda n: store.claim(str(n)), range(8)) if j]
    assert len(claimed) == 2
    assert len({j["workspace_id"] for j in claimed}) == 2


def test_restart_recovery_does_not_replay_ambiguous_billing(setup):
    store, a, b, _, _ = setup
    pure = store.enqueue(a["workspace_id"], a["user_id"], "index", {}, "pure")
    paid = store.enqueue(b["workspace_id"], b["user_id"], "report", {}, "paid", billable=True)
    store.claim("old-1"); store.claim("old-2")
    with store.connect(write=True) as db:
        db.execute("UPDATE jobs SET lease_until=0")
        db.execute("UPDATE jobs SET dispatch_started=1 WHERE id=?", (paid["id"],))
    restarted = Store(store.root)
    recovered = restarted.claim("new")
    assert recovered["id"] == pure["id"] and recovered["attempts"] == 2
    assert restarted.one("SELECT state FROM jobs WHERE id=?", (paid["id"],))["state"] == "needs_attention"
    with store.connect(write=True) as db:
        with pytest.raises(RuntimeError, match="lease_lost"):
            store.assert_lease(db, pure, "old-1")


def test_worker_atomic_index_and_relogin_summary(setup):
    store, a, _, ca, _ = setup
    p = store.ingest(a["workspace_id"], document())
    job = store.enqueue(a["workspace_id"], a["user_id"], "index", {}, "index", resource_id=p["paper_id"], version_id=p["version_id"])
    claimed = store.claim("worker")
    execute(store, claimed, "worker")
    assert store.one("SELECT state FROM jobs WHERE id=?", (job["id"],))["state"] == "succeeded"
    assert ca.put(f"/api/papers/{p['paper_id']}/summary", json={"content": "My persisted summary"}).status_code == 200
    old_cookie = ca.cookies.get("fastread_session")
    assert ca.post("/api/auth/logout").status_code == 200
    ca.cookies.set("fastread_session", old_cookie)
    assert ca.get("/api/papers").status_code == 401
    other_device = TestClient(ca.app)
    assert other_device.post("/api/auth/login", json={"email": "a@example.org", "password": "test-password-for-a"}).status_code == 200
    assert other_device.get(f"/api/papers/{p['paper_id']}").json()["summary"] == "My persisted summary"


def test_failed_login_limit_and_daily_budget(setup):
    store, a, _, ca, _ = setup
    for _ in range(8):
        assert ca.post("/api/auth/login", json={"email": "a@example.org", "password": "wrong"}).status_code == 401
    assert ca.post("/api/auth/login", json={"email": "a@example.org", "password": "wrong"}).status_code == 429
    with store.connect(write=True) as db:
        db.execute("UPDATE workspaces SET daily_limit=1 WHERE id=?", (a["workspace_id"],))
    store.enqueue(a["workspace_id"], a["user_id"], "report", {}, "first", billable=True)
    with pytest.raises(ValueError, match="daily_model_limit"):
        store.enqueue(a["workspace_id"], a["user_id"], "report", {}, "second", billable=True)


def test_identity_aliases_and_archive_permissions(setup):
    store, a, b, ca, cb = setup
    doc = document() | {"doi": None, "source_url": "https://arxiv.org/abs/2307.08691v1"}
    first = store.ingest(a["workspace_id"], doc)
    updated = document("Updated page with evidence for the same identified paper.") | {"doi": None, "source_url": "https://arxiv.org/abs/2307.08691v2"}
    second = store.ingest(a["workspace_id"], updated)
    assert second["paper_id"] == first["paper_id"]
    pid = first["paper_id"]
    assert cb.delete(f"/api/papers/{pid}").status_code == 404
    assert ca.delete(f"/api/papers/{pid}").status_code == 200
    assert ca.get(f"/api/papers/{pid}").status_code == 404
    assert ca.get('/api/papers?archived=true').json()['total'] == 1
    assert cb.post(f"/api/papers/{pid}/restore").status_code == 404
    assert ca.post(f"/api/papers/{pid}/restore").status_code == 200
    assert ca.get(f"/api/papers/{pid}").status_code == 200


def test_archive_waits_for_conversation_job(setup):
    store, a, _, ca, _ = setup
    p = store.ingest(a['workspace_id'], document())
    cid = ca.post(f"/api/papers/{p['paper_id']}/conversations").json()['id']
    store.enqueue(a['workspace_id'],a['user_id'],'chat',{},'pending-chat',resource_id=cid,version_id=p['version_id'])
    assert ca.delete(f"/api/papers/{p['paper_id']}").status_code == 409


def test_old_conversations_remain_accessible_after_document_update(setup):
    store, a, _, ca, cb = setup
    first=store.ingest(a['workspace_id'],document())
    pid=first['paper_id']
    old=ca.post(f'/api/papers/{pid}/conversations').json()
    second=store.ingest(a['workspace_id'],document('A second immutable document with corrected source evidence.'))
    current=ca.post(f'/api/papers/{pid}/conversations').json()
    assert old['id'] != current['id']
    rows=ca.get(f'/api/papers/{pid}/conversations').json()['items']
    assert {r['version_id'] for r in rows} == {first['version_id'],second['version_id']}
    assert cb.get(f'/api/papers/{pid}/conversations').status_code == 404


def test_version_vector_query_never_requires_legacy_artifact(setup, monkeypatch):
    from app.web.evidence import EvidenceRepository
    from app.services import vector_store
    store,a,_,_,_=setup
    p=store.ingest(a['workspace_id'],document())
    seen={}
    class Manager:
        def query(self, version, question, n_results, *, paper_result, chunks):
            seen.update(version=version,paper_result=paper_result,chunks=chunks)
            return [{'text':'version-scoped hit'}]
    monkeypatch.setattr(vector_store,'VectorStoreManager',Manager)
    repo=EvidenceRepository(store,a['workspace_id'],p['paper_id'],p['version_id'])
    assert repo.vector_query('evidence',5)
    assert seen['version']==p['version_id']
    assert seen['paper_result']['paper_document']['document_version_id']==p['version_id']
    assert seen['chunks']
