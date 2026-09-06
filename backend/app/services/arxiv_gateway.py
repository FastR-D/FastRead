"""Narrow transport routing for the optional FastRead arXiv gateway."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit, urlunsplit


ARXIV_HOSTS = frozenset({"arxiv.org", "www.arxiv.org", "export.arxiv.org"})
ARXIV_GATEWAY_KEY_HEADER = "X-FastRead-Gateway-Key"
_ARXIV_DOCUMENT_PATH = re.compile(r"^/(?:abs|pdf)/[A-Za-z0-9._/-]+$")


class ArxivGatewayConfigError(ValueError):
    """The configured arXiv-only gateway is incomplete or unsafe."""


@dataclass(frozen=True)
class ArxivRequestRoute:
    request_url: str
    headers: dict[str, str]
    via_gateway: bool


def is_arxiv_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    return parsed.scheme.lower() in {"http", "https"} and (
        parsed.hostname or ""
    ).lower() in ARXIV_HOSTS


def _allowed_arxiv_path(hostname: str, path: str) -> bool:
    if hostname == "export.arxiv.org" and path == "/api/query":
        return True
    return bool(_ARXIV_DOCUMENT_PATH.fullmatch(path))


def route_arxiv_request(
    url: str,
    *,
    gateway_url: str | None = None,
    api_key: str | None = None,
) -> ArxivRequestRoute:
    """Map only an official arXiv request onto the configured gateway.

    The gateway mirrors arXiv's ``/api/query``, ``/abs/<id>`` and
    ``/pdf/<id>`` paths.  No arbitrary destination URL is sent to it, which
    keeps this feature from becoming a general-purpose proxy.
    """

    original = str(url or "").strip()
    parsed = urlsplit(original)
    hostname = (parsed.hostname or "").lower()
    if hostname not in ARXIV_HOSTS:
        return ArxivRequestRoute(original, {}, False)

    configured_gateway = (
        os.getenv("ARXIV_GATEWAY_URL", "").strip()
        if gateway_url is None
        else str(gateway_url or "").strip()
    )
    if not configured_gateway:
        return ArxivRequestRoute(original, {}, False)
    if not _allowed_arxiv_path(hostname, parsed.path):
        raise ArxivGatewayConfigError(
            f"不支持的 arXiv 网关路径: {parsed.path or '/'}"
        )

    gateway = urlsplit(configured_gateway)
    if gateway.scheme.lower() != "https" or not gateway.hostname:
        raise ArxivGatewayConfigError("ARXIV_GATEWAY_URL 必须是有效的 HTTPS URL")
    if gateway.username or gateway.password or gateway.query or gateway.fragment:
        raise ArxivGatewayConfigError(
            "ARXIV_GATEWAY_URL 不能包含凭据、查询参数或片段"
        )
    configured_key = (
        os.getenv("ARXIV_GATEWAY_API_KEY", "").strip()
        if api_key is None
        else str(api_key or "").strip()
    )
    if not configured_key:
        raise ArxivGatewayConfigError(
            "配置 ARXIV_GATEWAY_URL 时必须同时配置 ARXIV_GATEWAY_API_KEY"
        )

    base_path = gateway.path.rstrip("/")
    routed_path = f"{base_path}{parsed.path}"
    request_url = urlunsplit(
        (gateway.scheme, gateway.netloc, routed_path, parsed.query, "")
    )
    return ArxivRequestRoute(
        request_url=request_url,
        headers={ARXIV_GATEWAY_KEY_HEADER: configured_key},
        via_gateway=True,
    )
