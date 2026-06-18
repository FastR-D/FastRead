import pytest
from fastapi import HTTPException

from app.routers.note import _assert_content_length_within_limit, _assert_public_image_url, _safe_upload_extension
from app.utils.local_access import require_local_request
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


def test_upload_extension_rejects_unsafe_file_type():
    with pytest.raises(HTTPException) as exc:
        _safe_upload_extension("../evil.exe")

    assert exc.value.status_code == 400


def test_content_length_limit_rejects_oversized_proxy_response():
    with pytest.raises(HTTPException) as exc:
        _assert_content_length_within_limit({"Content-Length": "20"}, 10)

    assert exc.value.status_code == 413


def test_content_length_limit_ignores_missing_or_invalid_header():
    _assert_content_length_within_limit({}, 10)
    _assert_content_length_within_limit({"Content-Length": "unknown"}, 10)


def test_image_proxy_rejects_loopback_url():
    with pytest.raises(HTTPException) as exc:
        _assert_public_image_url("http://127.0.0.1:8483/api/sys_health")

    assert exc.value.status_code == 403


def test_local_access_rejects_non_loopback_client():
    with pytest.raises(HTTPException) as exc:
        require_local_request(DummyRequest("8.8.8.8"))

    assert exc.value.status_code == 403


def test_local_access_allows_loopback_client():
    require_local_request(DummyRequest("127.0.0.1"))
