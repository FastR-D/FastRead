from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
from io import BytesIO
from importlib.metadata import PackageNotFoundError, version
import json
import os
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.academic_evidence import OFFICIAL_ACADEMIC_HOSTS, extract_document_academic_claim


SEARCH_TIMEOUT = float(os.getenv("PAPER_FETCH_TIMEOUT", "8"))


def normalize_canonical_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed._replace(fragment="").geturl()


FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 FastRead/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


FETCH_MAX_BYTES = _positive_env_int("FASTREAD_FETCH_MAX_BYTES", 20 * 1024 * 1024)
FETCH_MAX_REDIRECTS = _positive_env_int("FASTREAD_FETCH_MAX_REDIRECTS", 5)
TEXT_CHAR_LIMIT = 120000
PDF_PAGE_LIMIT = 80
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
METADATA_HOSTS = {
    "169.254.169.254",
    "100.100.100.200",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "instance-data.ec2.internal",
}

# Clash/Surge enhanced mode can resolve public hosts to RFC 2544 fake-IP
# addresses and transparently proxy them. These addresses are not routable to
# private infrastructure, so permit only this reserved range while keeping all
# other non-public addresses blocked.
FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _validate_public_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("only http/https source URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("source URLs containing credentials are not allowed")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise ValueError("source URL is missing a hostname")
    if hostname in METADATA_HOSTS or hostname.endswith(".metadata.google.internal"):
        raise ValueError("cloud metadata targets are not allowed")

    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0].split("%", 1)[0])
                for item in socket.getaddrinfo(
                    hostname,
                    parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except (OSError, ValueError) as exc:
            raise ValueError(f"source hostname cannot be resolved: {hostname}") from exc
    if not addresses:
        raise ValueError(f"source hostname cannot be resolved: {hostname}")
    for address in addresses:
        if str(address) in {"169.254.169.254", "100.100.100.200"}:
            raise ValueError(f"non-public source address is not allowed: {address}")
        if address in FAKE_IP_NETWORK:
            continue
        if not address.is_global:
            raise ValueError(f"non-public source address is not allowed: {address}")
    return parsed.geturl()


def _header(response, name: str) -> str:
    headers = getattr(response, "headers", {}) or {}
    value = headers.get(name) or headers.get(name.lower()) or headers.get(name.title())
    return str(value or "")


def _bounded_body(response, max_bytes: int, *, streaming: bool) -> bytes:
    content_length = _header(response, "content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ValueError(f"source response exceeds {max_bytes} bytes")
        except ValueError as exc:
            if "exceeds" in str(exc):
                raise

    if streaming and hasattr(response, "iter_bytes"):
        chunks = []
        total = 0
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"source response exceeds {max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    body = getattr(response, "content", b"")
    if not isinstance(body, bytes):
        body = bytes(body)
    if len(body) > max_bytes:
        raise ValueError(f"source response exceeds {max_bytes} bytes")
    return body


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


def _meta_contents(soup: BeautifulSoup, selector: str) -> list[str]:
    values = []
    try:
        nodes = soup.select(selector)
    except Exception:
        nodes = []
    for node in nodes:
        value = node.get("content") or node.get_text(" ", strip=True)
        value = str(value or "").strip()
        if value and value not in values:
            values.append(value)
    return values


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
    metadata = {
        "title": "", "publisher": "", "author": "", "published_at": "",
        "doi": "", "venue": "",
    }
    for item in objects:
        if not isinstance(item, dict):
            continue
        metadata["title"] = metadata["title"] or _jsonld_text(item.get("headline") or item.get("name"))
        metadata["publisher"] = metadata["publisher"] or _jsonld_resolved_text(item.get("publisher"), by_id)
        metadata["author"] = metadata["author"] or _jsonld_resolved_text(item.get("author") or item.get("creator"), by_id)
        metadata["published_at"] = metadata["published_at"] or _jsonld_text(
            item.get("datePublished") or item.get("dateCreated") or item.get("dateModified")
        )
        metadata["doi"] = metadata["doi"] or _jsonld_text(item.get("identifier") or item.get("sameAs"))
        metadata["venue"] = metadata["venue"] or _jsonld_text(item.get("isPartOf"))
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


def _html_snapshot(url: str, html: str, source_bytes: bytes | None = None) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    schema = _schema_metadata(soup)
    title = _meta_content(
        soup,
        "meta[name='citation_title']",
        "meta[property='og:title']",
        "meta[name='twitter:title']",
    ) or (
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
    authors = _meta_contents(soup, "meta[name='citation_author']")
    if not authors and author:
        authors = [author]
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
    doi = _meta_content(
        soup,
        "meta[name='citation_doi']",
        "meta[name='dc.identifier']",
        "meta[name='doi']",
    ) or schema.get("doi", "")
    venue = _meta_content(
        soup,
        "meta[name='citation_conference_title']",
        "meta[name='citation_journal_title']",
        "meta[name='prism.publicationName']",
    ) or schema.get("venue", "")
    pdf_url = _meta_content(soup, "meta[name='citation_pdf_url']")
    verified_academic_metadata = {
        "title": title,
        "authors": authors,
        "published_at": published_at,
        "venue": venue,
        "doi": doi,
        "source_url": url,
    }
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    official_record_verified = bool(
        host in OFFICIAL_ACADEMIC_HOSTS
        and title
        and authors
        and published_at
        and (venue or doi)
    )
    if not official_record_verified:
        verified_academic_metadata = {}

    _remove_noise(soup)
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    raw = source_bytes if source_bytes is not None else (html or "").encode("utf-8", errors="ignore")
    text_truncated = len(text) > TEXT_CHAR_LIMIT
    return {
        "url": url,
        "canonical_url": canonical,
        "title": title,
        "publisher": publisher,
        "author": author,
        "authors": authors,
        "published_at": published_at,
        "doi": doi,
        "venue": venue,
        "pdf_url": pdf_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "text": text[:TEXT_CHAR_LIMIT],
        "page_spans": [],
        "fetch_status": "ok" if text else "empty",
        "source_type": "web",
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "parser": "beautifulsoup4:html.parser",
        "parser_version": _package_version("beautifulsoup4"),
        "page_count_total": 1 if text else 0,
        "page_count_parsed": 1 if text else 0,
        "text_truncated": text_truncated,
        "extraction_limits": {"max_text_chars": TEXT_CHAR_LIMIT},
        "source_status": "parsed_partial" if text_truncated else "locked" if text else "blocked",
        "official_record_verified": official_record_verified,
        "verified_academic_metadata": verified_academic_metadata,
    }


def _pdf_text_with_spans(page_texts: list[str]) -> tuple[str, list[dict]]:
    chunks = []
    spans = []
    cursor = 0
    for index, raw_text in enumerate(page_texts, start=1):
        # Preserve line boundaries on PDF pages. First-page metadata parsing needs
        # layout signals to keep author, affiliation, address and email blocks out
        # of the title. Consumers that need prose can still collapse whitespace.
        page_text = "\n".join(
            re.sub(r"[ \t]+", " ", line).strip()
            for line in str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if line.strip()
        ).strip()
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
    pages = []
    page_spans = []
    status = "pdf_unparsed"
    pdf_metadata = {}
    parser = ""
    parser_version = ""
    page_count_total = 0
    page_count_parsed = 0
    try:
        import fitz

        with fitz.open(stream=content, filetype="pdf") as document:
            page_count_total = len(document)
            page_count_parsed = min(page_count_total, PDF_PAGE_LIMIT)
            pages = [
                document.load_page(index).get_text("text") or ""
                for index in range(page_count_parsed)
            ]
            pdf_metadata = document.metadata or {}
        parser = "pymupdf"
        parser_version = _package_version("PyMuPDF")
        text, page_spans = _pdf_text_with_spans(pages)
        status = "pdf_ok" if text else "empty"
    except Exception:
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            page_count_total = len(reader.pages)
            page_count_parsed = min(page_count_total, PDF_PAGE_LIMIT)
            pages = [page.extract_text() or "" for page in reader.pages[:PDF_PAGE_LIMIT]]
            text, page_spans = _pdf_text_with_spans(pages)
            metadata = reader.metadata or {}
            pdf_metadata = {str(key).lstrip("/").lower(): value for key, value in metadata.items()}
            parser = "pypdf"
            parser_version = _package_version("pypdf")
            status = "pdf_ok" if text else "empty"
        except Exception:
            try:
                import pdfplumber

                with pdfplumber.open(BytesIO(content)) as pdf:
                    page_count_total = len(pdf.pages)
                    page_count_parsed = min(page_count_total, PDF_PAGE_LIMIT)
                    pages = [(page.extract_text() or "") for page in pdf.pages[:PDF_PAGE_LIMIT]]
                    text, page_spans = _pdf_text_with_spans(pages)
                parser = "pdfplumber"
                parser_version = _package_version("pdfplumber")
                status = "pdf_ok" if text else "empty"
            except Exception:
                text = ""
                page_spans = []
                status = "pdf_unparsed"

    document_claimed_metadata = extract_document_academic_claim(pages[0] if pages else "")
    claimed_title = str(document_claimed_metadata.get("title") or "")
    claimed_authors = document_claimed_metadata.get("authors") or []
    claimed_year = document_claimed_metadata.get("year")
    claimed_venue = str(document_claimed_metadata.get("venue") or "")
    text_truncated = len(text) > TEXT_CHAR_LIMIT or page_count_total > page_count_parsed
    clipped_spans = [
        {**span, "end": min(int(span["end"]), TEXT_CHAR_LIMIT)}
        for span in page_spans
        if int(span["start"]) < TEXT_CHAR_LIMIT
    ]
    return {
        "url": url,
        "canonical_url": normalize_canonical_url(url),
        "title": str(pdf_metadata.get("title") or claimed_title),
        "publisher": "",
        "author": str(pdf_metadata.get("author") or ""),
        "authors": [str(pdf_metadata.get("author"))] if pdf_metadata.get("author") else claimed_authors,
        "published_at": str(claimed_year or pdf_metadata.get("creationDate") or pdf_metadata.get("creationdate") or ""),
        "doi": "",
        "venue": claimed_venue,
        "pdf_url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "text": text[:TEXT_CHAR_LIMIT],
        "page_spans": clipped_spans,
        "fetch_status": status,
        "source_type": "pdf",
        "content_hash": hashlib.sha256(content).hexdigest(),
        "source_bytes": len(content),
        "parser": parser,
        "parser_version": parser_version,
        "page_count_total": page_count_total,
        "page_count_parsed": page_count_parsed,
        "text_truncated": text_truncated,
        "extraction_limits": {
            "max_pages": PDF_PAGE_LIMIT,
            "max_text_chars": TEXT_CHAR_LIMIT,
        },
        "source_status": (
            "parsed_partial" if status == "pdf_ok" and text_truncated
            else "locked" if status == "pdf_ok"
            else "blocked"
        ),
        "official_record_verified": False,
        "verified_academic_metadata": {},
        "document_claimed_metadata": document_claimed_metadata,
    }


def parse_pdf_bytes(content: bytes, url: str = "") -> dict:
    return _pdf_snapshot(url, content)


def fetch_source_snapshot(
    url: str,
    result: dict | None = None,
    client_factory=None,
    *,
    max_bytes: int | None = None,
    max_redirects: int | None = None,
) -> dict:
    result = result or {}
    supplement = {
        key: value
        for key, value in result.items()
        if value not in (None, "", [])
    }
    byte_limit = max(1, int(max_bytes or FETCH_MAX_BYTES))
    redirect_limit = max(0, int(max_redirects if max_redirects is not None else FETCH_MAX_REDIRECTS))
    if not url:
        return {
            "url": "",
            "canonical_url": "",
            "title": "",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "text": "",
            "fetch_status": "failed",
            "source_type": "web",
            "source_status": "blocked",
            "unverified_supplement": supplement,
        }
    try:
        factory = client_factory or httpx.Client
        with factory(timeout=SEARCH_TIMEOUT, headers=FETCH_HEADERS, follow_redirects=False) as client:
            if callable(getattr(client, "stream", None)):
                current_url = _validate_public_url(url)
                redirect_chain = []
                body = b""
                content_type = ""
                encoding = "utf-8"
                final_url = current_url
                for redirect_count in range(redirect_limit + 1):
                    current_url = _validate_public_url(current_url)
                    if not redirect_chain or redirect_chain[-1] != current_url:
                        redirect_chain.append(current_url)
                    with client.stream("GET", current_url) as response:
                        response_url = str(getattr(response, "url", current_url) or current_url)
                        response_url = _validate_public_url(response_url)
                        status_code = int(getattr(response, "status_code", 200) or 200)
                        location = _header(response, "location")
                        if status_code in REDIRECT_STATUSES:
                            if not location:
                                raise ValueError("redirect response is missing a Location header")
                            if redirect_count >= redirect_limit:
                                raise ValueError(f"source redirect limit exceeded ({redirect_limit})")
                            current_url = _validate_public_url(urljoin(response_url, location))
                            continue
                        response.raise_for_status()
                        body = _bounded_body(response, byte_limit, streaming=True)
                        content_type = _header(response, "content-type").lower()
                        encoding = getattr(response, "encoding", None) or "utf-8"
                        final_url = response_url
                        if redirect_chain[-1] != final_url:
                            redirect_chain.append(final_url)
                        break
                else:
                    raise ValueError(f"source redirect limit exceeded ({redirect_limit})")
            else:
                # Compatibility path for injected legacy clients. Production uses the
                # streaming/manual-redirect branch above.
                _validate_public_url(url)
                response = client.get(url)
                response.raise_for_status()
                final_url = str(getattr(response, "url", url) or url)
                redirect_chain = [
                    str(getattr(item, "url", "") or "")
                    for item in getattr(response, "history", []) or []
                    if str(getattr(item, "url", "") or "")
                ]
                if not redirect_chain:
                    redirect_chain.append(url)
                if final_url != redirect_chain[-1]:
                    redirect_chain.append(final_url)
                if len(redirect_chain) - 1 > redirect_limit:
                    raise ValueError(f"source redirect limit exceeded ({redirect_limit})")
                for visited_url in redirect_chain:
                    _validate_public_url(visited_url)
                body = _bounded_body(response, byte_limit, streaming=False)
                content_type = _header(response, "content-type").lower()
                encoding = getattr(response, "encoding", None) or "utf-8"

            if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
                snapshot = _pdf_snapshot(final_url, body)
            else:
                html = body.decode(encoding, errors="ignore") if isinstance(body, bytes) else str(body)
                snapshot = _html_snapshot(final_url, html, source_bytes=body)
                parsed_final = urlparse(final_url)
                if (
                    parsed_final.hostname in {"arxiv.org", "www.arxiv.org"}
                    and parsed_final.path.startswith("/abs/")
                    and snapshot.get("pdf_url")
                ):
                    pdf_snapshot = fetch_source_snapshot(
                        urljoin(final_url, snapshot["pdf_url"]),
                        {**result, "title": snapshot.get("title") or result.get("title", "")},
                        client_factory=factory,
                        max_bytes=byte_limit,
                        max_redirects=redirect_limit,
                    )
                    if pdf_snapshot.get("fetch_status") == "pdf_ok":
                        pdf_snapshot.update(
                            {
                                "title": snapshot.get("title") or pdf_snapshot.get("title") or "",
                                "authors": snapshot.get("authors") or pdf_snapshot.get("authors") or [],
                                "author": snapshot.get("author") or pdf_snapshot.get("author") or "",
                                "published_at": snapshot.get("published_at") or pdf_snapshot.get("published_at") or "",
                                "doi": snapshot.get("doi") or pdf_snapshot.get("doi") or "",
                                "venue": snapshot.get("venue") or pdf_snapshot.get("venue") or "",
                                "source_page_url": final_url,
                            }
                        )
                        snapshot = pdf_snapshot
            snapshot["redirect_chain"] = redirect_chain
            snapshot["unverified_supplement"] = supplement
            return snapshot
    except Exception as exc:
        return {
            "url": url,
            "canonical_url": normalize_canonical_url(url),
            "title": "",
            "publisher": "",
            "author": "",
            "authors": [],
            "published_at": "",
            "doi": "",
            "venue": "",
            "pdf_url": "",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "text": "",
            "fetch_status": "failed",
            "source_type": "web",
            "source_status": "blocked",
            "official_record_verified": False,
            "verified_academic_metadata": {},
            "unverified_supplement": supplement,
            "error": str(exc)[:240],
        }
