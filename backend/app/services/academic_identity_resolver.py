from __future__ import annotations

from datetime import datetime, timezone
import json
import re

import httpx
from bs4 import BeautifulSoup


PAPERCOPILOT_ENDPOINT = "https://papercopilot.com/wp-admin/admin-ajax.php"
ACCEPTED_ICLR_STATUSES = {"oral", "poster", "spotlight"}
TITLE_STOPWORDS = {"a", "an", "and", "of", "the", "for", "in", "on", "to", "with"}


def _normalized_title(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _search_term(title: str) -> str:
    for token in _normalized_title(title).split():
        if token not in TITLE_STOPWORDS and len(token) >= 5:
            return token
    return ""


def resolve_document_claim_record(
    claim: dict | None,
    *,
    client_factory=None,
) -> dict:
    """Resolve an ICLR document claim through an accepted-paper index linked to OpenReview."""
    claim = claim or {}
    venue = claim.get("venue_metadata") or {}
    if venue.get("id") != "iclr":
        return {}

    title = str(claim.get("title") or "").strip()
    year = int(claim.get("year") or 0)
    term = _search_term(title)
    if not title or not year or not term:
        return {}

    filters = json.dumps(
        [{"colIndex": 1, "terms": [term]}],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    params = {
        "action": "load_paperlist",
        "batch": 0,
        "conf": "iclr",
        "year": year,
        "mode": "rating",
        "track": "main",
        "surface": "papers",
        "filters": filters,
        "review_dims": '["rating"]',
        "review_metric_search": "raw",
        "review_metric_search_map": '{"rating":"raw"}',
    }
    factory = client_factory or httpx.Client
    with factory(timeout=12, follow_redirects=True) as client:
        response = client.get(PAPERCOPILOT_ENDPOINT, params=params)
        response.raise_for_status()
        payload = response.json()

    soup = BeautifulSoup(str(payload.get("html") or ""), "html.parser")
    expected_title = _normalized_title(title)
    for row in soup.select("tr"):
        link = row.select_one('a[href*="openreview.net/forum"]')
        status_cell = row.select_one(".pc-status-cell")
        if not link or not status_cell:
            continue
        record_title = link.get_text(" ", strip=True)
        status = str(status_cell.get("title") or status_cell.get_text(" ", strip=True)).strip()
        record_url = str(link.get("href") or "").strip()
        if _normalized_title(record_title) != expected_title:
            continue
        if status.casefold() not in ACCEPTED_ICLR_STATUSES:
            continue
        if not record_url.startswith("https://openreview.net/forum?id="):
            continue

        return {
            "registry_record_verified": True,
            "registry_name": "Paper Copilot ICLR accepted-paper index",
            "registry_record_url": record_url,
            "registry_retrieved_at": datetime.now(timezone.utc).isoformat(),
            "verified_academic_metadata": {
                "title": record_title,
                "authors": claim.get("authors") or [],
                "published_at": str(year),
                "year": year,
                "venue": f"ICLR {year}",
                "source_url": record_url,
                "publication_status": status,
            },
        }
    return {}
