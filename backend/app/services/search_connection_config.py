from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from app.db.provider_dao import get_provider_by_id, insert_provider, update_provider
from app.services.secret_store import unprotect_secret


_PROXY_PROVIDER_ID = "__fastread_paper_search_proxy__"
_SCHOLAR_PROVIDER_ID = "__fastread_google_scholar__"
_ELASTICSEARCH_PROVIDER_ID = "__fastread_elasticsearch__"
_SYSTEM_PROVIDER_TYPE = "system-search-connection"


@dataclass(frozen=True)
class SearchConnectionConfig:
    paper_search_proxy_url: str
    google_scholar_api_url: str
    serpapi_api_key: str
    elasticsearch_url: str

    def public_dict(self) -> dict:
        values = asdict(self)
        values.pop("serpapi_api_key")
        values["serpapi_api_key_configured"] = bool(self.serpapi_api_key)
        return values


def _stored_value(provider_id: str, attribute: str, env_name: str) -> str:
    row = get_provider_by_id(provider_id)
    if row is None:
        return os.getenv(env_name, "").strip()
    value = getattr(row, attribute, "") or ""
    if attribute == "api_key":
        value = unprotect_secret(value)
    return str(value).strip()


def get_search_connection_config() -> SearchConnectionConfig:
    """Return the effective search connection settings.

    A saved (even empty) database value takes precedence over environment
    variables. This lets the Settings page explicitly disable a value inherited
    from a developer shell without modifying process-global environment state.
    """
    return SearchConnectionConfig(
        paper_search_proxy_url=_stored_value(
            _PROXY_PROVIDER_ID, "base_url", "PAPER_SEARCH_PROXY_URL"
        ),
        google_scholar_api_url=_stored_value(
            _SCHOLAR_PROVIDER_ID, "base_url", "GOOGLE_SCHOLAR_API_URL"
        ),
        serpapi_api_key=_stored_value(
            _SCHOLAR_PROVIDER_ID, "api_key", "SERPAPI_API_KEY"
        ),
        elasticsearch_url=_stored_value(
            _ELASTICSEARCH_PROVIDER_ID, "base_url", "ELASTICSEARCH_URL"
        ),
    )


def _validate_url(name: str, value: str, schemes: set[str]) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in schemes or not parsed.hostname:
        allowed = "/".join(sorted(schemes))
        raise ValueError(f"{name} 必须是有效的 {allowed} URL")
    return value.rstrip("/")


def _upsert_system_provider(
    provider_id: str,
    name: str,
    *,
    base_url: str,
    api_key: str | None = None,
) -> None:
    row = get_provider_by_id(provider_id)
    if row is None:
        insert_provider(
            id=provider_id,
            name=name,
            api_key=api_key or "",
            base_url=base_url,
            logo="custom",
            type_=_SYSTEM_PROVIDER_TYPE,
            enabled=1,
        )
        return
    fields: dict[str, str | int] = {"base_url": base_url, "enabled": 1}
    if api_key is not None:
        fields["api_key"] = api_key
    update_provider(provider_id, **fields)


def save_search_connection_config(
    *,
    paper_search_proxy_url: str,
    google_scholar_api_url: str,
    elasticsearch_url: str,
    serpapi_api_key: str | None = None,
    clear_serpapi_api_key: bool = False,
) -> SearchConnectionConfig:
    proxy_url = _validate_url(
        "PAPER_SEARCH_PROXY_URL",
        paper_search_proxy_url,
        {"http", "https"},
    )
    scholar_url = _validate_url(
        "GOOGLE_SCHOLAR_API_URL", google_scholar_api_url, {"http", "https"}
    )
    elastic_url = _validate_url(
        "ELASTICSEARCH_URL", elasticsearch_url, {"http", "https"}
    )

    _upsert_system_provider(
        _PROXY_PROVIDER_ID,
        "PAPER_SEARCH_PROXY_URL",
        base_url=proxy_url,
    )
    scholar_key: str | None
    if clear_serpapi_api_key:
        scholar_key = ""
    elif serpapi_api_key is None or not serpapi_api_key.strip():
        scholar_key = None
    else:
        scholar_key = serpapi_api_key.strip()
    _upsert_system_provider(
        _SCHOLAR_PROVIDER_ID,
        "GOOGLE_SCHOLAR_API_URL / SERPAPI_API_KEY",
        base_url=scholar_url,
        api_key=scholar_key,
    )
    _upsert_system_provider(
        _ELASTICSEARCH_PROVIDER_ID,
        "ELASTICSEARCH_URL",
        base_url=elastic_url,
    )
    return get_search_connection_config()


def is_system_search_provider(row) -> bool:
    return bool(row and getattr(row, "type", "") == _SYSTEM_PROVIDER_TYPE)
