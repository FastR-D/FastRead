from urllib.parse import parse_qs, urlsplit

import pytest

from app.services.arxiv_gateway import (
    ARXIV_GATEWAY_KEY_HEADER,
    ArxivGatewayConfigError,
    route_arxiv_request,
)
from app.services import paper_fetching
from app.services.paper_search_service import InvertedIndex, PaperSearchService


def test_gateway_routes_only_supported_arxiv_paths(monkeypatch):
    monkeypatch.setenv("ARXIV_GATEWAY_URL", "https://sg-arxiv.example/gateway")
    monkeypatch.setenv("ARXIV_GATEWAY_API_KEY", "test-secret")

    route = route_arxiv_request(
        "https://export.arxiv.org/api/query?search_query=all%3Aagent&max_results=1"
    )

    parsed = urlsplit(route.request_url)
    assert route.via_gateway is True
    assert parsed.netloc == "sg-arxiv.example"
    assert parsed.path == "/gateway/api/query"
    assert parse_qs(parsed.query) == {
        "search_query": ["all:agent"],
        "max_results": ["1"],
    }
    assert route.headers == {ARXIV_GATEWAY_KEY_HEADER: "test-secret"}

    direct = route_arxiv_request("https://api.crossref.org/works")
    assert direct.via_gateway is False
    assert direct.headers == {}


def test_gateway_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("ARXIV_GATEWAY_URL", "http://8.219.149.159")
    monkeypatch.setenv("ARXIV_GATEWAY_API_KEY", "test-secret")
    with pytest.raises(ArxivGatewayConfigError, match="HTTPS"):
        route_arxiv_request("https://arxiv.org/pdf/1706.03762.pdf")

    monkeypatch.setenv("ARXIV_GATEWAY_URL", "https://sg-arxiv.example")
    monkeypatch.delenv("ARXIV_GATEWAY_API_KEY", raising=False)
    with pytest.raises(ArxivGatewayConfigError, match="API_KEY"):
        route_arxiv_request("https://arxiv.org/abs/1706.03762")


class _GatewayResponse:
    status_code = 200
    text = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    content = text.encode()

    def raise_for_status(self):
        return None


class _GatewayClient:
    calls = []
    last_init_kwargs = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        type(self).last_init_kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _GatewayResponse()


def test_paper_search_uses_gateway_without_general_proxy(monkeypatch, tmp_path):
    monkeypatch.setenv("ARXIV_GATEWAY_URL", "https://sg-arxiv.example")
    monkeypatch.setenv("ARXIV_GATEWAY_API_KEY", "test-secret")
    _GatewayClient.calls = []
    _GatewayClient.last_init_kwargs = {}
    service = PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "index.json"),
        client_factory=_GatewayClient,
        proxy_url="",
        require_proxy=True,
    )

    papers, status = service._fetch_arxiv("agent", ("ai",), 1)

    assert papers == []
    assert status["available"] is True
    assert status["provider"] == "arxiv_gateway"
    url, request = _GatewayClient.calls[0]
    assert url.startswith("https://sg-arxiv.example/api/query?")
    assert request["headers"][ARXIV_GATEWAY_KEY_HEADER] == "test-secret"
    assert "proxy" not in _GatewayClient.last_init_kwargs


class _PdfResponse:
    status_code = 200
    headers = {"content-type": "application/pdf"}
    encoding = "utf-8"

    def __init__(self, url):
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield b"%PDF-test"


class _GatewayPdfClient:
    calls = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _PdfResponse(url)


def test_direct_arxiv_pdf_import_uses_gateway_and_preserves_source_url(monkeypatch):
    original = "https://arxiv.org/pdf/1706.03762.pdf"
    monkeypatch.setenv("ARXIV_GATEWAY_URL", "https://sg-arxiv.example")
    monkeypatch.setenv("ARXIV_GATEWAY_API_KEY", "test-secret")
    monkeypatch.setattr(paper_fetching, "_validate_public_url", lambda url: url)
    monkeypatch.setattr(
        paper_fetching,
        "_pdf_snapshot",
        lambda url, content: {
            "url": url,
            "canonical_url": url,
            "pdf_url": url,
            "fetch_status": "pdf_ok",
            "source_type": "pdf",
            "source_bytes": len(content),
        },
    )
    _GatewayPdfClient.calls = []

    snapshot = paper_fetching.fetch_source_snapshot(
        original, client_factory=_GatewayPdfClient
    )

    method, request_url, request = _GatewayPdfClient.calls[0]
    assert method == "GET"
    assert request_url == "https://sg-arxiv.example/pdf/1706.03762.pdf"
    assert request["headers"][ARXIV_GATEWAY_KEY_HEADER] == "test-secret"
    assert snapshot["fetch_status"] == "pdf_ok"
    assert snapshot["url"] == original
    assert snapshot["canonical_url"] == original
