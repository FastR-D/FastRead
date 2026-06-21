from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import re

import httpx
from bs4 import BeautifulSoup

from app.services.verification.constants import SEARCH_TIMEOUT
from app.services.verification.source_intel import normalize_canonical_url


FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ReelMindVerifier/2.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str:
    for selector in selectors:
        try:
            node = soup.select_one(selector)
        except Exception:
            node = None
        if not node:
            continue
        value = ""
        try:
            value = (
                node.get("content")
                or node.get("datetime")
                or node.get("href")
                or node.get_text(" ", strip=True)
            )
        except Exception:
            value = ""
        if value:
            return str(value).strip()
    return ""


def _jsonld_items(value) -> list[dict]:
    items = []
    if isinstance(value, list):
        for item in value:
            items.extend(_jsonld_items(item))
    elif isinstance(value, dict):
        items.append(value)
        graph = value.get("@graph")
        if graph:
            items.extend(_jsonld_items(graph))
    return items


def _jsonld_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "headline", "alternateName"):
            text = _jsonld_text(value.get(key))
            if text:
                return text
    if isinstance(value, list):
        for item in value:
            text = _jsonld_text(item)
            if text:
                return text
    return ""


def _jsonld_id(value) -> str:
    if isinstance(value, dict):
        raw = value.get("@id") or value.get("id")
        return str(raw).strip() if raw else ""
    if isinstance(value, str) and value.startswith("#"):
        return value.strip()
    return ""


def _jsonld_resolved_text(value, by_id: dict[str, dict]) -> str:
    text = _jsonld_text(value)
    if text:
        return text
    if isinstance(value, list):
        for item in value:
            text = _jsonld_resolved_text(item, by_id)
            if text:
                return text
    ref = _jsonld_id(value)
    if ref and ref in by_id:
        return _jsonld_text(by_id[ref])
    return ""


def _schema_metadata(soup: BeautifulSoup) -> dict:
    objects = []
    for node in soup.select("script[type='application/ld+json']"):
        raw = node.string or node.get_text("", strip=False)
        if not raw:
            continue
        try:
            objects.extend(_jsonld_items(json.loads(raw)))
        except Exception:
            continue

    by_id = {
        ref: item
        for item in objects
        if isinstance(item, dict)
        for ref in [_jsonld_id(item)]
        if ref
    }
    metadata = {"title": "", "publisher": "", "author": "", "published_at": ""}
    for item in objects:
        if not isinstance(item, dict):
            continue
        metadata["title"] = metadata["title"] or _jsonld_text(item.get("headline") or item.get("name"))
        metadata["publisher"] = metadata["publisher"] or _jsonld_resolved_text(item.get("publisher"), by_id)
        metadata["author"] = metadata["author"] or _jsonld_resolved_text(item.get("author") or item.get("creator"), by_id)
        metadata["published_at"] = metadata["published_at"] or _jsonld_text(
            item.get("datePublished") or item.get("dateCreated") or item.get("dateModified")
        )
        if metadata["title"] and metadata["publisher"] and metadata["author"] and metadata["published_at"]:
            break
    return metadata


def _remove_noise(soup: BeautifulSoup) -> None:
    for selector in ("script", "style", "noscript", "nav", "footer", "aside", "form", "iframe"):
        try:
            for node in soup.select(selector):
                node.decompose()
        except Exception:
            continue


def _html_snapshot(url: str, html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    schema = _schema_metadata(soup)
    title = _meta_content(soup, "meta[property='og:title']", "meta[name='twitter:title']") or (
        soup.title.get_text(" ", strip=True) if getattr(soup, "title", None) else ""
    ) or schema.get("title", "")
    canonical = _meta_content(soup, "link[rel='canonical']") or normalize_canonical_url(url)
    author = _meta_content(
        soup,
        "meta[name='author']",
        "meta[property='article:author']",
        "meta[name='dc.creator']",
        "meta[name='citation_author']",
    ) or schema.get("author", "")
    publisher = _meta_content(
        soup,
        "meta[property='og:site_name']",
        "meta[name='publisher']",
        "meta[property='article:publisher']",
        "meta[name='dc.publisher']",
        "meta[name='citation_publisher']",
    ) or schema.get("publisher", "")
    published_at = _meta_content(
        soup,
        "meta[property='article:published_time']",
        "meta[property='article:modified_time']",
        "meta[name='date']",
        "meta[name='pubdate']",
        "meta[name='dc.date']",
        "meta[name='citation_publication_date']",
        "meta[name='citation_online_date']",
        "time[datetime]",
    ) or schema.get("published_at", "")
    _remove_noise(soup)
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "url": url,
        "canonical_url": canonical,
        "title": title,
        "publisher": publisher,
        "author": author,
        "published_at": published_at,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "text": text[:120000],
        "page_spans": [],
        "fetch_status": "ok" if text else "empty",
        "source_type": "web",
    }


def _pdf_text_with_spans(page_texts: list[str]) -> tuple[str, list[dict]]:
    chunks = []
    spans = []
    cursor = 0
    for index, raw_text in enumerate(page_texts, start=1):
        page_text = re.sub(r"\s+", " ", raw_text or "").strip()
        if not page_text:
            continue
        if chunks:
            chunks.append(" ")
            cursor += 1
        start = cursor
        chunks.append(page_text)
        cursor += len(page_text)
        spans.append({"page": index, "start": start, "end": cursor})
    return "".join(chunks).strip(), spans


def _pdf_snapshot(url: str, content: bytes) -> dict:
    text = ""
    page_spans = []
    status = "pdf_unparsed"
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages = []
        for page in reader.pages[:30]:
            pages.append(page.extract_text() or "")
        text, page_spans = _pdf_text_with_spans(pages)
        status = "pdf_ok" if text else "empty"
    except Exception:
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(content)) as pdf:
                text, page_spans = _pdf_text_with_spans([(page.extract_text() or "") for page in pdf.pages[:30]])
            status = "pdf_ok" if text else "empty"
        except Exception:
            text = ""
            page_spans = []
            status = "pdf_unparsed"

    return {
        "url": url,
        "canonical_url": normalize_canonical_url(url),
        "title": "",
        "publisher": "",
        "author": "",
        "published_at": "",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "text": text[:120000],
        "page_spans": [span for span in page_spans if span["start"] < 120000],
        "fetch_status": status,
        "source_type": "pdf",
    }


def fetch_source_snapshot(url: str, result: dict | None = None, client_factory=None) -> dict:
    result = result or {}
    if not url:
        return {
            "url": "",
            "canonical_url": "",
            "title": result.get("title") or "",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "text": "",
            "fetch_status": "failed",
            "source_type": "web",
        }
    try:
        factory = client_factory or httpx.Client
        with factory(timeout=SEARCH_TIMEOUT, headers=FETCH_HEADERS, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            final_url = str(getattr(response, "url", url) or url)
            redirect_chain = [
                str(getattr(item, "url", "") or "")
                for item in getattr(response, "history", []) or []
                if str(getattr(item, "url", "") or "")
            ]
            if final_url:
                redirect_chain.append(final_url)
            body = response.content
            if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
                snapshot = _pdf_snapshot(final_url, body)
            else:
                encoding = getattr(response, "encoding", None) or "utf-8"
                html = body.decode(encoding, errors="ignore") if isinstance(body, bytes) else str(body)
                snapshot = _html_snapshot(final_url, html)
            if not snapshot.get("title"):
                snapshot["title"] = result.get("title") or ""
            snapshot["redirect_chain"] = redirect_chain
            return snapshot
    except Exception as exc:
        return {
            "url": url,
            "canonical_url": normalize_canonical_url(url),
            "title": result.get("title") or "",
            "publisher": result.get("publisher") or "",
            "author": result.get("author") or "",
            "published_at": result.get("published_at") or "",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "text": "",
            "fetch_status": "failed",
            "source_type": "web",
            "error": str(exc)[:240],
        }
