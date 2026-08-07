from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_AUTHORITATIVE_DOMAINS: dict[str, dict[str, str]] = {
    "who.int": {"tier": "A", "label": "World Health Organization"},
    "iarc.who.int": {"tier": "A", "label": "International Agency for Research on Cancer"},
    "fda.gov": {"tier": "A", "label": "U.S. Food and Drug Administration"},
    "cdc.gov": {"tier": "A", "label": "U.S. Centers for Disease Control and Prevention"},
    "sec.gov": {"tier": "A", "label": "U.S. Securities and Exchange Commission"},
    "stats.gov.cn": {"tier": "A", "label": "National Bureau of Statistics of China"},
    "pubmed.ncbi.nlm.nih.gov": {"tier": "A", "label": "PubMed"},
    "pmc.ncbi.nlm.nih.gov": {"tier": "A", "label": "PubMed Central"},
    "ncbi.nlm.nih.gov": {"tier": "A", "label": "NCBI"},
    "reuters.com": {"tier": "B", "label": "Reuters"},
    "apnews.com": {"tier": "B", "label": "Associated Press"},
    "nature.com": {"tier": "B", "label": "Nature"},
    "science.org": {"tier": "B", "label": "Science"},
}

DEFAULT_BLOCKED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
}

DEFAULT_RISKY_DOMAINS = {
    "top10-example.com": "content_farm",
    "rank-example.com": "content_farm",
    "blog-example.com": "content_farm",
}

DEFAULT_AUTHORITY_BRAND_TOKENS: dict[str, tuple[str, ...]] = {
    "who": ("who.int", "iarc.who.int"),
    "iarc": ("iarc.who.int",),
    "fda": ("fda.gov",),
    "cdc": ("cdc.gov",),
    "sec": ("sec.gov",),
    "pubmed": ("pubmed.ncbi.nlm.nih.gov",),
    "ncbi": ("ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"),
}


REGISTRY_PATH = Path(__file__).with_name("source_registry_data.json")


def _normalized_registry(raw: dict | None = None) -> dict:
    raw = raw or {}
    authoritative = dict(DEFAULT_AUTHORITATIVE_DOMAINS)
    for domain, metadata in (raw.get("authoritative_domains") or {}).items():
        if not isinstance(metadata, dict):
            continue
        tier = str(metadata.get("tier") or "").upper()
        label = str(metadata.get("label") or domain)
        if tier in {"A", "B", "C", "D", "BLOCKED"}:
            authoritative[str(domain).lower()] = {"tier": "blocked" if tier == "BLOCKED" else tier, "label": label}

    blocked = {str(item).lower() for item in DEFAULT_BLOCKED_DOMAINS}
    blocked.update(str(item).lower() for item in (raw.get("blocked_domains") or []) if item)

    risky = dict(DEFAULT_RISKY_DOMAINS)
    for domain, flag in (raw.get("risky_domains") or {}).items():
        if domain and flag:
            risky[str(domain).lower()] = str(flag)

    brand_tokens = {key: tuple(value) for key, value in DEFAULT_AUTHORITY_BRAND_TOKENS.items()}
    for token, domains in (raw.get("authority_brand_tokens") or {}).items():
        if isinstance(domains, str):
            domains = [domains]
        if token and domains:
            brand_tokens[str(token).lower()] = tuple(str(domain).lower() for domain in domains if domain)

    return {
        "authoritative_domains": authoritative,
        "blocked_domains": blocked,
        "risky_domains": risky,
        "authority_brand_tokens": brand_tokens,
    }


@lru_cache(maxsize=1)
def registry_data() -> dict:
    try:
        with REGISTRY_PATH.open("r", encoding="utf-8") as f:
            return _normalized_registry(json.load(f))
    except Exception:
        return _normalized_registry()


AUTHORITATIVE_DOMAINS = registry_data()["authoritative_domains"]
BLOCKED_DOMAINS = registry_data()["blocked_domains"]
RISKY_DOMAINS = registry_data()["risky_domains"]
AUTHORITY_BRAND_TOKENS = registry_data()["authority_brand_tokens"]


def domain_from_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    return host.split(":", 1)[0].removeprefix("www.")


def domain_matches(domain: str, registered_domain: str) -> bool:
    domain = (domain or "").lower().removeprefix("www.")
    registered_domain = (registered_domain or "").lower().removeprefix("www.")
    return domain == registered_domain or domain.endswith(f".{registered_domain}")


def lookup_domain(domain: str) -> dict[str, str] | None:
    for registered_domain, metadata in AUTHORITATIVE_DOMAINS.items():
        if domain_matches(domain, registered_domain):
            return {"domain": registered_domain, **metadata}
    return None


def risky_domain_flag(domain: str) -> str:
    for registered_domain, flag in RISKY_DOMAINS.items():
        if domain_matches(domain, registered_domain):
            return flag
    return ""


def is_allowed_authority_domain(domain: str, allowed_domains: tuple[str, ...]) -> bool:
    return any(domain_matches(domain, allowed) for allowed in allowed_domains)


def _contains_brand_token(text: str, token: str) -> bool:
    if not text or not token:
        return False
    return bool(
        re.search(rf"(?<![a-z0-9]){re.escape(token.lower())}(?![a-z0-9])", text.lower())
    )


def detect_fake_authority(domain: str, title: str = "", publisher: str = "") -> bool:
    domain = (domain or "").lower().removeprefix("www.")
    publisher_text = (publisher or "").lower()
    title_text = (title or "").lower()
    official_title_claim = bool(
        re.search(
            r"official|press release|official release|statement|公告|官方|权威发布|新闻稿",
            title_text,
            re.I,
        )
    )
    for token, allowed_domains in AUTHORITY_BRAND_TOKENS.items():
        if not is_allowed_authority_domain(domain, allowed_domains):
            if _contains_brand_token(domain, token) or _contains_brand_token(publisher_text, token):
                return True
            if official_title_claim and _contains_brand_token(title_text, token):
                return True
    return False


def detect_canonical_anomaly(original_url: str, fetched_url: str, canonical_url: str) -> bool:
    original_domain = domain_from_url(original_url)
    fetched_domain = domain_from_url(fetched_url)
    canonical_domain = domain_from_url(canonical_url)
    if not original_domain:
        return False
    if canonical_domain and not domain_matches(canonical_domain, original_domain):
        return True
    if fetched_domain and not domain_matches(fetched_domain, original_domain):
        return True
    return False
