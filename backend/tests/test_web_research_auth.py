import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.web.api import create_web_app
from app.web.auth import SSO_EXPIRED, consume_research_ticket, research_placeholder_email


KEY_A = "aabbccddeeff00112233"
KEY_B = "00112233445566778899"
KEY_C = "112233445566778899aa"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTREAD_COOKIE_SECURE", "false")
    monkeypatch.setenv("FASTRESEARCH_API_URL", "http://research.test")
    monkeypatch.setenv("FASTRESEARCH_PANEL_URL", "http://127.0.0.1:5173")
    return create_web_app(tmp_path)


def install_consumer(monkeypatch, mapping):
    def consume(ticket):
        identity = mapping.get(ticket)
        if not identity:
            raise HTTPException(401, SSO_EXPIRED)
        return identity

    monkeypatch.setattr("app.web.auth.consume_research_ticket", consume)


def sign_in(client, ticket):
    response = client.post("/api/auth/research", json={"ticket": ticket})
    if response.status_code == 200:
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response


def test_login_info_exposes_panel_url(app):
    client = TestClient(app)
    data = client.get("/api/auth/login-info").json()
    assert data == {"mode": "fastresearch-key", "panel_url": "http://127.0.0.1:5173"}
    assert client.post("/api/auth/login", json={"email": "a@example.org", "password": "test-password-for-a"}).status_code == 404


def test_research_login_upserts_by_key_id(app, monkeypatch):
    install_consumer(
        monkeypatch,
        {
            "first": {"key_id": KEY_A, "person": "张三"},
            "again": {"key_id": KEY_A, "person": "张三（更新）"},
            "other": {"key_id": KEY_B, "person": "李四"},
        },
    )
    alice = TestClient(app)
    first = sign_in(alice, "first")
    assert first.status_code == 200
    me = alice.get("/api/auth/me").json()
    assert me["display_name"] == "张三"
    assert me["research_key_id"] == KEY_A
    assert me["email"] == research_placeholder_email(KEY_A)
    workspace = me["workspace_id"]

    again = TestClient(app)
    assert sign_in(again, "again").status_code == 200
    me_again = again.get("/api/auth/me").json()
    assert me_again["workspace_id"] == workspace
    assert me_again["display_name"] == "张三（更新）"
    assert me_again["research_key_id"] == KEY_A

    bob = TestClient(app)
    assert sign_in(bob, "other").status_code == 200
    me_bob = bob.get("/api/auth/me").json()
    assert me_bob["workspace_id"] != workspace
    assert me_bob["research_key_id"] == KEY_B
    assert alice.get("/api/papers").status_code == 200
    assert bob.get("/api/papers").status_code == 200


def test_research_login_upserts_by_stable_account_id(app, monkeypatch):
    install_consumer(
        monkeypatch,
        {
            "first": {"key_id": KEY_A, "account_id": "account-alice", "person": "张三"},
            "rotated": {"key_id": KEY_C, "account_id": "account-alice", "person": "张三（新 Key）"},
            "other": {"key_id": KEY_B, "account_id": "account-bob", "person": "李四"},
        },
    )
    alice = TestClient(app)
    assert sign_in(alice, "first").status_code == 200
    first = alice.get("/api/auth/me").json()
    workspace = first["workspace_id"]
    user = first["email"]
    assert first["research_account_id"] == "account-alice"

    rotated = TestClient(app)
    assert sign_in(rotated, "rotated").status_code == 200
    again = rotated.get("/api/auth/me").json()
    assert again["workspace_id"] == workspace
    assert again["email"] == user
    assert again["display_name"] == "张三（新 Key）"
    assert again["research_account_id"] == "account-alice"

    bob = TestClient(app)
    assert sign_in(bob, "other").status_code == 200
    assert bob.get("/api/auth/me").json()["workspace_id"] != workspace


def test_invalid_research_ticket_stays_logged_out(app, monkeypatch):
    install_consumer(monkeypatch, {})
    client = TestClient(app)
    response = sign_in(client, "expired")
    assert response.status_code == 401
    assert response.json()["detail"] == SSO_EXPIRED
    assert client.get("/api/auth/me").status_code == 401
    assert sign_in(client, "").status_code == 401


def test_research_login_does_not_lock_loopback_on_invalid_tickets(app, monkeypatch):
    install_consumer(monkeypatch, {"good": {"key_id": KEY_A, "person": "Alice"}})
    client = TestClient(app)
    for _ in range(12):
        assert sign_in(client, "expired").status_code == 401
    assert sign_in(client, "good").status_code == 200


def test_consume_posts_fast_read_audience(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout, trust_env=True):
        seen.update(url=url, json=json, timeout=timeout, trust_env=trust_env)
        return FakeResponse(200, {"keyId": KEY_A, "person": "张三"})

    monkeypatch.setenv("FASTRESEARCH_API_URL", "http://research.test/")
    monkeypatch.setattr("app.web.auth.httpx.post", fake_post)
    identity = consume_research_ticket("ticket-1")
    assert seen["url"] == "http://research.test/api/sso/consume"
    assert seen["json"] == {"ticket": "ticket-1", "audience": "fast-read"}
    assert seen["timeout"] == 5
    assert seen["trust_env"] is False
    assert identity == {"key_id": KEY_A, "person": "张三"}


def test_consume_reads_stable_account_id(monkeypatch):
    def fake_post(url, json, timeout, trust_env=True):
        return FakeResponse(200, {"keyId": KEY_A, "accountId": "account-alice", "person": "张三"})

    monkeypatch.setenv("FASTRESEARCH_API_URL", "http://research.test")
    monkeypatch.setattr("app.web.auth.httpx.post", fake_post)
    assert consume_research_ticket("ticket-1") == {
        "key_id": KEY_A,
        "account_id": "account-alice",
        "person": "张三",
    }


def test_consume_rejects_invalid_payload(monkeypatch):
    monkeypatch.setenv("FASTRESEARCH_API_URL", "http://research.test")

    def fake_post(url, json, timeout, trust_env=True):
        return FakeResponse(200, {"keyId": "not-a-key", "person": "张三"})

    monkeypatch.setattr("app.web.auth.httpx.post", fake_post)
    with pytest.raises(HTTPException) as rejected:
        consume_research_ticket("ticket-1")
    assert rejected.value.status_code == 401
    assert rejected.value.detail == SSO_EXPIRED


def test_consume_maps_research_outage(monkeypatch):
    monkeypatch.setenv("FASTRESEARCH_API_URL", "http://research.test")

    def fake_post(url, json, timeout, trust_env=True):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.web.auth.httpx.post", fake_post)
    with pytest.raises(HTTPException) as rejected:
        consume_research_ticket("ticket-1")
    assert rejected.value.status_code == 503


def test_anonymous_document_redirects_to_panel(app):
    client = TestClient(app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "http://127.0.0.1:5173"


def test_sso_document_consumes_ticket_and_sets_cookie(app, monkeypatch):
    install_consumer(monkeypatch, {"first": {"key_id": KEY_A, "person": "Alice"}})
    client = TestClient(app, follow_redirects=False)
    response = client.get("/?sso=first")
    assert response.status_code == 302
    assert "sso=" not in response.headers["location"]
    assert response.headers["location"].endswith("/")
    assert "fastread_session=" in response.headers.get("set-cookie", "")
    follow = client.get("/")
    assert follow.status_code != 302


def test_invalid_sso_document_bounces_to_panel(app, monkeypatch):
    install_consumer(monkeypatch, {})
    client = TestClient(app, follow_redirects=False)
    response = client.get("/?sso=expired")
    assert response.status_code == 302
    assert response.headers["location"] == "http://127.0.0.1:5173"


def test_frontend_origin_can_exchange_ticket(app, monkeypatch):
    install_consumer(monkeypatch, {"first": {"key_id": KEY_A, "person": "Alice"}})
    client = TestClient(app)
    response = client.post(
        "/api/auth/research",
        json={"ticket": "first"},
        headers={"Origin": "http://127.0.0.1:3015"},
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me", headers={"Origin": "http://127.0.0.1:3015"}).status_code == 200


def test_unknown_origin_cannot_exchange_ticket(app, monkeypatch):
    install_consumer(monkeypatch, {"first": {"key_id": KEY_A, "person": "Alice"}})
    client = TestClient(app)
    response = client.post(
        "/api/auth/research",
        json={"ticket": "first"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403


def test_session_document_is_not_redirected(app, monkeypatch):
    install_consumer(monkeypatch, {"first": {"key_id": KEY_A, "person": "张三"}})
    client = TestClient(app, follow_redirects=False)
    assert sign_in(client, "first").status_code == 200
    response = client.get("/")
    assert response.status_code != 302


def test_health_is_not_redirected(app):
    client = TestClient(app, follow_redirects=False)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert client.get("/api/auth/login-info").status_code == 200

