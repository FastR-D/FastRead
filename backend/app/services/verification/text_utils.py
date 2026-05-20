from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from app.services.verification.constants import (
    AUTHORITY_TITLE_HINTS,
    GENERIC_SEARCH_TERMS,
    LOW_VALUE_SOURCE_HINTS,
    TRUSTED_DOMAIN_HINTS,
)


def tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    words = set(re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    grams = {chinese[i:i + 2] for i in range(max(len(chinese) - 1, 0))}
    return {token for token in words | grams if len(token) >= 2}


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def clean_result_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def is_trusted_source(title: str, url: str) -> bool:
    result_domain = domain(url)
    title_text = title or ""
    if any(hint in result_domain for hint in LOW_VALUE_SOURCE_HINTS):
        return False
    return any(hint in result_domain for hint in TRUSTED_DOMAIN_HINTS) or any(
        hint in title_text for hint in AUTHORITY_TITLE_HINTS
    )


def result_item(title: str, url: str, snippet: str = "") -> dict:
    return {
        "title": title[:160],
        "url": url,
        "domain": domain(url),
        "snippet": snippet[:260],
        "trusted": is_trusted_source(title, url),
    }


def strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(str(text), "html.parser").get_text(" ", strip=True)


def is_low_value_result(result: dict, claim: str) -> bool:
    result_domain = result.get("domain") or domain(result.get("url") or "")
    title = result.get("title") or ""
    if any(hint in result_domain for hint in LOW_VALUE_SOURCE_HINTS):
        claim_tokens = tokenize(claim) - GENERIC_SEARCH_TERMS
        result_tokens = tokenize(f"{title} {result.get('snippet', '')}")
        return len(claim_tokens & result_tokens) < 4
    return False
