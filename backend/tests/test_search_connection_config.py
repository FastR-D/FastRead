import json
from types import SimpleNamespace

import pytest

from app.routers import search_config as search_config_router
from app.services import search_connection_config as search_config


def _fake_provider_store(monkeypatch):
    rows = {}

    def get_provider(provider_id):
        return rows.get(provider_id)

    def insert_provider(id, name, api_key, base_url, logo, type_, enabled=1):
        rows[id] = SimpleNamespace(
            id=id,
            name=name,
            api_key=api_key,
            base_url=base_url,
            logo=logo,
            type=type_,
            enabled=enabled,
        )
        return id

    def update_provider(provider_id, **fields):
        for key, value in fields.items():
            setattr(rows[provider_id], key, value)

    monkeypatch.setattr(search_config, "get_provider_by_id", get_provider)
    monkeypatch.setattr(search_config, "insert_provider", insert_provider)
    monkeypatch.setattr(search_config, "update_provider", update_provider)
    return rows


def test_saved_search_connections_override_environment_and_do_not_expose_key(monkeypatch):
    _fake_provider_store(monkeypatch)
    monkeypatch.setenv("PAPER_SEARCH_PROXY_URL", "http://127.0.0.1:1111")
    monkeypatch.setenv("SERPAPI_API_KEY", "environment-secret")

    saved = search_config.save_search_connection_config(
        paper_search_proxy_url="http://127.0.0.1:10808",
        google_scholar_api_url="https://scholar.example.test/api",
        serpapi_api_key="saved-secret",
        elasticsearch_url="http://127.0.0.1:9200",
    )

    assert saved.paper_search_proxy_url == "http://127.0.0.1:10808"
    assert saved.serpapi_api_key == "saved-secret"
    assert saved.public_dict() == {
        "paper_search_proxy_url": "http://127.0.0.1:10808",
        "google_scholar_api_url": "https://scholar.example.test/api",
        "elasticsearch_url": "http://127.0.0.1:9200",
        "serpapi_api_key_configured": True,
    }


def test_blank_key_keeps_existing_secret_and_explicit_clear_removes_it(monkeypatch):
    _fake_provider_store(monkeypatch)
    common = {
        "paper_search_proxy_url": "",
        "google_scholar_api_url": "",
        "elasticsearch_url": "",
    }
    search_config.save_search_connection_config(**common, serpapi_api_key="secret")
    assert search_config.save_search_connection_config(**common).serpapi_api_key == "secret"
    assert search_config.save_search_connection_config(
        **common, clear_serpapi_api_key=True
    ).serpapi_api_key == ""


@pytest.mark.parametrize("value", ["127.0.0.1:7890", "ftp://127.0.0.1:21"])
def test_proxy_url_requires_a_supported_scheme(monkeypatch, value):
    _fake_provider_store(monkeypatch)
    with pytest.raises(ValueError, match="PAPER_SEARCH_PROXY_URL"):
        search_config.save_search_connection_config(
            paper_search_proxy_url=value,
            google_scholar_api_url="",
            elasticsearch_url="",
        )


def test_config_endpoint_never_echoes_serpapi_key(monkeypatch):
    monkeypatch.setattr(
        search_config_router,
        "get_search_connection_config",
        lambda: search_config.SearchConnectionConfig("", "", "top-secret", ""),
    )
    response = search_config_router.get_paper_search_config()
    payload = json.loads(response.body)["data"]

    assert payload["serpapi_api_key_configured"] is True
    assert "serpapi_api_key" not in payload
    assert "top-secret" not in response.body.decode("utf-8")
