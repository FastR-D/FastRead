import asyncio

import pytest
from fastapi import HTTPException

from app.utils.local_access import LocalOnlyASGI, require_local_request
from app.utils.response import ResponseWrapper as R


class DummyClient:
    def __init__(self, host):
        self.host = host


class DummyRequest:
    def __init__(self, host):
        self.client = DummyClient(host)


def test_response_error_uses_http_status_from_http_code():
    response = R.error(msg="missing", code=404)

    assert response.status_code == 404


def test_response_error_maps_business_code_to_bad_request():
    response = R.error(msg="bad", code=200101)

    assert response.status_code == 400


def test_local_access_rejects_non_loopback_client():
    with pytest.raises(HTTPException) as exc:
        require_local_request(DummyRequest("8.8.8.8"))

    assert exc.value.status_code == 403


def test_local_access_allows_loopback_client():
    require_local_request(DummyRequest("127.0.0.1"))


def test_mounted_static_gate_rejects_non_loopback_client(monkeypatch):
    called = False
    messages = []

    async def downstream(_scope, _receive, _send):
        nonlocal called
        called = True

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    monkeypatch.delenv("ALLOW_NON_LOCAL_ADMIN", raising=False)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/uploads/paper.pdf",
        "headers": [],
        "client": ("192.168.1.25", 50123),
    }

    asyncio.run(LocalOnlyASGI(downstream)(scope, receive, send))

    assert called is False
    assert messages[0]["status"] == 403
