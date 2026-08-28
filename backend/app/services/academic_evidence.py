from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse


from app.services.venue_catalog import (
    ai_venue_ids,
    allowed_venue_catalog,
    match_allowed_venue,
    security_venue_ids,
    systems_venue_ids,
)


OFFICIAL_ACADEMIC_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "proceedings.mlr.press",
    "openreview.net",
    "papers.nips.cc",
    "aclanthology.org",
    "ojs.aaai.org",
    "usenix.org",
    "www.usenix.org",
    "ndss-symposium.org",
    "www.ndss-symposium.org",
    "doi.org",
}

PREPRINT_HOST_HINTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "ssrn.com")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def normalize_venue(value: str | None) -> dict:
    matched = match_allowed_venue(value)
    if matched["id"]:
        return matched
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return {"id": "", "name": text, "short_name": text, "track": "", "raw": text}


def normalize_doi(value: str | None, *fallback_values: str | None) -> str:
    candidates = (value, *fallback_values)
    for candidate in candidates:
        text = unquote(str(candidate or "")).strip()
        match = DOI_RE.search(text)
        if match:
            return match.group(0).rstrip(".,;)").lower()
    return ""


def _normalize_authors(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if ";" in text:
        return [item.strip() for item in text.split(";") if item.strip()]
    return [text]


def _publication_year(value: str | None) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return int(match.group(0)) if match else None


FORMAL_PUBLICATION_CLAIM_RE = re.compile(
    r"(?:published\s+as\s+(?:a\s+)?conference\s+paper\s+at|accepted\s+(?:for|at)|"
    r"to\s+appear\s+(?:at|in)|proceedings\s+of)\s+(?P<venue>[^\n]{2,160})",
    re.IGNORECASE,
)


def _clean_document_title(lines: list[str]) -> str:
    title = " ".join(lines).strip()
    title = re.sub(r"(?<=[A-Za-z])-\s+(?=[A-Za-z])", "", title)
    return re.sub(r"\s+", " ", title).strip(" -")[:240]


def _document_authors(line: str) -> list[str]:
    cleaned = re.sub(r"[\d*†‡§¶∗]+", "", str(line or ""))
    values = re.split(r"\s*(?:,|\band\b)\s*", cleaned, flags=re.IGNORECASE)
    return [
        value.strip(" .;:")
        for value in values
        if len(value.strip(" .;:").split()) >= 2
    ]


def extract_document_academic_claim(first_page_text: str | None) -> dict:
    """Extract document-asserted identity without promoting it to an official record."""
    raw_text = str(first_page_text or "")
    if not raw_text.strip():
        return {}

    lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    header_index = next(
        (index for index, line in enumerate(lines[:20]) if FORMAL_PUBLICATION_CLAIM_RE.search(line)),
        None,
    )
    header = lines[header_index] if header_index is not None else ""
    venue = match_allowed_venue(header, " ".join(lines[:20]))
    if not venue.get("id"):
        return {}

    abstract_index = next(
        (index for index, line in enumerate(lines[:40]) if line.casefold() == "abstract"),
        min(len(lines), 12),
    )
    start_index = (header_index + 1) if header_index is not None else 0
    identity_lines = lines[start_index:abstract_index]
    author_index = next(
        (
            index
            for index, line in enumerate(identity_lines)
            if ("," in line or re.search(r"\band\b", line, re.IGNORECASE))
            and line.upper() != line
            and len(_document_authors(line)) >= 1
        ),
        None,
    )
    title_lines = identity_lines[:author_index] if author_index is not None else identity_lines[:3]
    title = _clean_document_title(title_lines)
    authors = _document_authors(identity_lines[author_index]) if author_index is not None else []
    year = _publication_year(header or " ".join(lines[:8]))
    formal_claim = bool(header and FORMAL_PUBLICATION_CLAIM_RE.search(header))

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "published_at": str(year or ""),
        "venue": venue.get("short_name") or venue.get("name") or venue.get("raw") or "",
        "venue_metadata": venue,
        "publication_status": "document_claimed_published" if formal_claim else "document_venue_detected",
        "claim_text": header,
        "source": "document_first_page",
        "formal_publication_claim": formal_claim,
    }


def assess_academic_identity(metadata: dict | None) -> dict:
    metadata = metadata or {}
    has_fetch_provenance = (
        "official_record_verified" in metadata
        or "verified_academic_metadata" in metadata
        or "registry_record_verified" in metadata
    )
    record_verified = bool(
        metadata.get("official_record_verified") is True
        or metadata.get("registry_record_verified") is True
    )
    verified_metadata = (
        metadata.get("verified_academic_metadata")
        if record_verified
        and isinstance(metadata.get("verified_academic_metadata"), dict)
        else {}
    )
    document_claimed_metadata = (
        metadata.get("document_claimed_metadata")
        if isinstance(metadata.get("document_claimed_metadata"), dict)
        else {}
    )
    identity_metadata = (
        verified_metadata
        if verified_metadata
        else document_claimed_metadata
        if document_claimed_metadata
        else metadata
        if not has_fetch_provenance
        else {}
    )
    url = str(
        identity_metadata.get("source_url")
        or metadata.get("url")
        or metadata.get("canonical_url")
        or ""
    )
    domain = (urlparse(url).hostname or "").lower()
    title = str(identity_metadata.get("title") or "").strip()
    authors = _normalize_authors(identity_metadata.get("authors") or identity_metadata.get("author"))
    published_at = str(identity_metadata.get("published_at") or "").strip()
    year = _publication_year(identity_metadata.get("year") or published_at)
    venue = normalize_venue(
        identity_metadata.get("venue")
        or identity_metadata.get("conference")
        or identity_metadata.get("journal")
    )
    doi = normalize_doi(identity_metadata.get("doi"), identity_metadata.get("identifier"))
    status_text = " ".join(
        str(source.get(key) or "")
        for source in (metadata, identity_metadata)
        for key in ("publication_status", "title", "notice", "status")
    ).lower()

    is_withdrawn = any(token in status_text for token in ("withdrawn", "撤回"))
    is_retracted = any(token in status_text for token in ("retracted", "撤稿")) or is_withdrawn
    is_preprint = any(hint in domain for hint in PREPRINT_HOST_HINTS) or "preprint" in status_text or "预印本" in status_text
    official_host_match = domain in OFFICIAL_ACADEMIC_HOSTS
    official_record = bool(
        official_host_match
        and record_verified
        and verified_metadata
    )
    supplement = metadata.get("unverified_supplement") or {}
    has_academic_signal = bool(
        metadata.get("document_type") == "paper"
        or metadata.get("paper_task")
        or metadata.get("doi")
        or metadata.get("venue")
        or supplement
        or domain in OFFICIAL_ACADEMIC_HOSTS
        or is_preprint
    )
    identity_fields_complete = bool(title and authors and year)
    identity_complete = bool(identity_fields_complete and official_record)
    is_top4_security = venue.get("track") == "security"
    is_core_venue = bool(venue["id"])
    venue_track = venue.get("track") or ""
    track_label = {
        "security": "安全",
        "systems": "系统",
        "ai": "AI",
    }.get(venue_track, "核心")
    formal_identity_passed = bool(identity_complete and not is_retracted and not is_preprint)
    gate_passed = bool(formal_identity_passed and is_core_venue)

    if gate_passed:
        level = "A1"
        label = f"{track_label}顶会正式论文，身份完整"
    elif formal_identity_passed:
        level = "A2"
        label = "正式论文，身份完整但不属于安全、系统或 AI 核心顶会"
    elif is_preprint and title and authors and year:
        level = "B1"
        label = "预印本，身份可识别但未经核心顶会正式发表 Gate"
    elif is_core_venue:
        level = "U"
        venue_label = venue.get("short_name") or venue.get("name") or venue.get("raw") or "核心顶会"
        label = f"已识别 {venue_label}（{track_label}顶会），待官方记录核验"
    elif has_academic_signal:
        level = "U"
        label = "学术身份不完整"
    else:
        level = "N/A"
        label = "非学术来源或无可识别论文元数据"

    warnings = []
    if level != "N/A":
        if not title:
            warnings.append("missing_title")
        if not authors:
            warnings.append("missing_authors")
        if not year:
            warnings.append("missing_year")
        if not official_record:
            warnings.append("missing_verified_official_record")
        if document_claimed_metadata and not official_record:
            warnings.append("document_claim_not_official_record")
        if not is_core_venue:
            warnings.append("not_core_venue")
        if is_preprint:
            warnings.append("preprint_not_formal_venue_record")
        if is_retracted:
            warnings.append("retracted_or_withdrawn")

    identity_status = (
        "officially_aligned" if identity_complete
        else "incomplete" if has_academic_signal
        else "unrecognized"
    )
    integrity_status = (
        "withdrawn" if is_withdrawn
        else "retracted" if is_retracted
        else "preprint" if is_preprint
        else "clear" if official_record
        else "unknown"
    )

    return {
        "level": level,
        "label": label,
        "gate_passed": gate_passed,
        "formal_identity_passed": formal_identity_passed,
        "identity_complete": identity_complete,
        "identity_fields_complete": identity_fields_complete,
        "is_top4_security": is_top4_security,
        "is_core_venue": is_core_venue,
        "venue_track": venue_track,
        "identity_source": (
            "official_record"
            if official_record and metadata.get("official_record_verified") is True
            else "conference_registry"
            if official_record and metadata.get("registry_record_verified") is True
            else "document_claim"
            if document_claimed_metadata
            else "provided_metadata"
            if identity_metadata
            else "unknown"
        ),
        "identity_status": identity_status,
        "publication_status": (
            "withdrawn" if is_withdrawn
            else "retracted" if is_retracted
            else "preprint" if is_preprint
            else "formally_published" if official_record
            else "unknown"
        ),
        "integrity_status": integrity_status,
        "source_status": metadata.get("source_status") or "blocked",
        "title": title,
        "authors": authors,
        "year": year,
        "doi": doi,
        "venue": venue,
        "official_record": official_record,
        "official_record_verified": metadata.get("official_record_verified") is True,
        "registry_record_verified": metadata.get("registry_record_verified") is True,
        "registry_name": str(metadata.get("registry_name") or ""),
        "registry_record_url": str(metadata.get("registry_record_url") or ""),
        "official_host_match": official_host_match,
        "verified_metadata_used": bool(verified_metadata),
        "document_claimed_metadata": document_claimed_metadata,
        "has_academic_signal": has_academic_signal,
        "warnings": warnings,
    }
