from __future__ import annotations

"""Versioned, replayable metadata normalization for every paper ingestion path."""

from datetime import datetime, timezone
import re
from urllib.parse import urlparse

from app.services.academic_evidence import assess_academic_identity, normalize_doi, normalize_venue


METADATA_SCHEMA_VERSION = "paper-metadata-v2"
METADATA_PARSER_VERSION = "first-page-layout-v3"
METADATA_STRATEGY_VERSION = "verified-overlay-v2"

_EMAIL_RE = re.compile(r"(?:mailto:)?[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_ADDRESS_RE = re.compile(
    r"\b(?:university|institute|laboratory|department|school|college|corporation|corp\.?|"
    r"street|st\.?|road|rd\.?|avenue|ave\.?|boulevard|city|state|province|country|"
    r"california|beijing|shanghai|china|usa|united states|postal|zip|inc\.?|ltd\.?|company)\b",
    re.IGNORECASE,
)
_ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", re.IGNORECASE)
_ADDRESS_LINE_RE = re.compile(r",\s*[A-Z]{2,3}\s*,|\b\d{5}(?:-\d{4})?\b")
_FOOTNOTE_RE = re.compile(r"^(?:[*†‡§¶∗]|\d+[.)]?\s*)+")
_ABSTRACT_RE = re.compile(r"^(?:abstract|summary)\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?\s*)?(?:introduction|abstract)\b", re.IGNORECASE)
_VENUE_RE = re.compile(
    r"(?:published\s+as|accepted\s+(?:at|for)|to\s+appear|proceedings\s+of|conference\s+paper)",
    re.IGNORECASE,
)
_NAME_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z'`.-]*(?:-[A-Z][A-Za-z'`.-]*)?$|^[A-Z]\.?$")
_NAME_FUNCTION_WORDS = {"a", "an", "and", "as", "at", "for", "from", "in", "is", "of", "on", "the", "to", "with"}


def _clean_line(value: str) -> str:
    value = _FOOTNOTE_RE.sub("", str(value or "").strip())
    return re.sub(r"\s+", " ", value).strip(" ,;|")


def _is_noise_line(line: str) -> bool:
    return bool(
        not line
        or _EMAIL_RE.search(line)
        or _ORCID_RE.search(line)
        or _ADDRESS_RE.search(line)
        or line.casefold().startswith(("corresponding author", "equal contribution", "affiliation"))
    )


def _looks_like_author_piece(value: str) -> bool:
    value = re.sub(r"[\d*†‡§¶∗]+", "", value).strip(" ,;:")
    tokens = [token for token in value.split() if token]
    if not 2 <= len(tokens) <= 6 or _is_noise_line(value) or any(mark in value for mark in ("?", ":")):
        return False
    if {token.strip("(),.:;?").casefold() for token in tokens} & _NAME_FUNCTION_WORDS:
        return False
    name_tokens = sum(bool(_NAME_TOKEN_RE.fullmatch(token.strip("(),"))) for token in tokens)
    return name_tokens >= max(2, len(tokens) - 1)


def _author_pieces(line: str) -> list[str]:
    return [
        piece.strip()
        for piece in re.split(r"\s*(?:,|;|\band\b|\s{2,})\s*", line, flags=re.IGNORECASE)
        if piece.strip()
    ]


def _looks_like_multi_author_line(line: str) -> bool:
    pieces = _author_pieces(line)
    return len(pieces) >= 2 and sum(_looks_like_author_piece(piece) for piece in pieces) >= 2


def _authors_from_lines(lines: list[str]) -> list[str]:
    authors: list[str] = []
    for line in lines:
        if _EMAIL_RE.search(line) or _ORCID_RE.search(line):
            continue
        if _ADDRESS_LINE_RE.search(line):
            continue
        affiliation = _ADDRESS_RE.search(line)
        if affiliation:
            prefix = line[: affiliation.start()].strip(" ,;:-")
            affiliation_kind = affiliation.group(0).casefold().rstrip(".")
            if affiliation_kind in {"department", "laboratory"} and _looks_like_author_piece(prefix) and prefix not in authors:
                authors.append(prefix)
            continue
        pieces = _author_pieces(line)
        if len(pieces) == 1 and _looks_like_author_piece(line):
            pieces = [line]
        for piece in pieces:
            cleaned = re.sub(r"[\d*†‡§¶∗]+", "", piece).strip(" .;:")
            if _looks_like_author_piece(cleaned) and cleaned not in authors:
                authors.append(cleaned)
    return authors[:50]


def first_page_candidates(first_page_text: str | None) -> dict:
    """Produce code-owned title/author boundaries; models may only select among them."""
    lines = [_clean_line(line) for line in str(first_page_text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return {"title_candidates": [], "author_candidates": [], "boundary_reason": "empty_first_page"}

    abstract_index = next(
        (index for index, line in enumerate(lines[:80]) if _ABSTRACT_RE.match(line)),
        min(len(lines), 40),
    )
    opening = lines[:abstract_index]
    venue_index = next((i for i, line in enumerate(opening[:20]) if _VENUE_RE.search(line)), None)
    if venue_index is not None:
        opening = opening[venue_index + 1 :]

    usable = [line for line in opening if not _SECTION_RE.match(line)]
    author_start = next((i for i, line in enumerate(usable) if _looks_like_multi_author_line(line)), None)
    if author_start is None:
        single_flags = [_looks_like_author_piece(line) for line in usable]
        for index in range(1, len(usable) - 1):
            if single_flags[index] and single_flags[index + 1]:
                prefix = " ".join(usable[:index])
                if len(prefix) >= 8:
                    author_start = index
                    break
    title_lines = usable[:author_start] if author_start is not None else usable[:4]
    author_lines = usable[author_start:] if author_start is not None else []
    title_lines = [line for line in title_lines if not _is_noise_line(line)]

    candidates: list[str] = []
    for width in range(1, min(4, len(title_lines)) + 1):
        title = " ".join(title_lines[:width])
        title = re.sub(r"(?<=[A-Za-z])-\s+(?=[A-Za-z])", "", title)
        title = re.sub(r"\s+", " ", title).strip(" -")[:300]
        if 8 <= len(title) <= 300 and title not in candidates:
            candidates.append(title)
    authors = _authors_from_lines(author_lines)
    return {
        "title_candidates": candidates,
        "author_candidates": authors,
        "boundary_reason": "author_boundary_detected" if author_start is not None else "opening_block_fallback",
    }


def _metadata_view(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        key: raw.get(key)
        for key in (
            "title", "author", "authors", "published_at", "year", "venue", "doi", "identifier",
            "url", "canonical_url", "pdf_url", "source_type", "source_status", "content_hash",
            "parser", "parser_version", "document_claimed_metadata", "official_record_verified",
            "registry_record_verified", "verified_academic_metadata", "registry_name", "registry_record_url",
        )
        if raw.get(key) not in (None, "", [])
    }


def normalize_paper_metadata(
    raw_metadata: dict | None,
    *,
    first_page_text: str = "",
    unverified_supplement: dict | None = None,
    resolved_identity: dict | None = None,
) -> dict:
    raw = _metadata_view(raw_metadata)
    supplement = {k: v for k, v in (unverified_supplement or {}).items() if v not in (None, "", [])}
    resolved = {k: v for k, v in (resolved_identity or {}).items() if v not in (None, "", [], {})}
    candidates = first_page_candidates(first_page_text)
    claimed = raw.get("document_claimed_metadata") or {}
    verified = resolved.get("verified_academic_metadata") or raw.get("verified_academic_metadata") or {}
    verified_record = bool(
        resolved.get("registry_record_verified")
        or resolved.get("official_record_verified")
        or raw.get("registry_record_verified")
        or raw.get("official_record_verified")
    )

    fallback_reasons: list[str] = []
    title = str(verified.get("title") if verified_record else "").strip()
    title_source = "verified_identity" if title else ""
    if not title:
        candidate_title = candidates["title_candidates"][-1] if candidates["title_candidates"] else ""
        claimed_title = str(claimed.get("title") or "").strip()
        raw_title = str(raw.get("title") or "").strip()
        supplement_title = str(supplement.get("title") or "").strip()
        candidate_key = re.sub(r"[^a-z0-9]+", "", candidate_title.casefold())
        claimed_key = re.sub(r"[^a-z0-9]+", "", claimed_title.casefold())
        raw_key = re.sub(r"[^a-z0-9]+", "", raw_title.casefold())
        if raw_key and candidate_key and (raw_key.startswith(candidate_key) or candidate_key.startswith(raw_key)):
            title = min((raw_title, candidate_title), key=len)
            title_source = "raw_candidate_prefix_reconciliation"
        elif raw_title:
            title = raw_title
            title_source = "structured_raw_metadata"
        elif supplement_title and not claimed_title:
            title = supplement_title
            title_source = "unverified_supplement_fallback"
        elif candidate_key and claimed_key and (candidate_key.startswith(claimed_key) or claimed_key.startswith(candidate_key)):
            title = min((candidate_title, claimed_title), key=len)
            title_source = "code_claim_prefix_reconciliation"
        elif candidate_title:
            title = candidate_title
            title_source = "code_candidate_boundary"
        elif claimed_title:
            title = claimed_title
            title_source = "document_claim"
        if title and claimed_title:
            title_key = re.sub(r"[^a-z0-9]+", "", title.casefold())
            if title_key.startswith(claimed_key) or claimed_key.startswith(title_key):
                reconciled = min((title, claimed_title), key=len)
                if reconciled != title:
                    title = reconciled
                    title_source = "claim_prefix_reconciliation"
    if not title:
        title = str(raw.get("title") or supplement.get("title") or "未命名论文").strip()
        title_source = "raw_or_unverified_fallback"
        fallback_reasons.append("title_candidate_missing")

    authors = verified.get("authors") if verified_record else []
    authors_source = "verified_identity" if authors else ""
    if not authors:
        authors = candidates["author_candidates"] or claimed.get("authors") or []
        authors_source = "code_candidates_or_document_claim" if authors else ""
    if not authors:
        authors = raw.get("authors") or ([raw.get("author")] if raw.get("author") else []) or supplement.get("authors") or []
        authors_source = "raw_or_unverified_fallback"
        fallback_reasons.append("author_candidates_missing")
    authors = [str(author).strip() for author in authors if str(author).strip() and not _is_noise_line(str(author))]

    published = verified.get("published_at") if verified_record else claimed.get("published_at") or raw.get("published_at")
    year_match = re.search(r"\b(?:19|20)\d{2}\b", str(verified.get("year") or published or claimed.get("year") or raw.get("year") or supplement.get("year") or ""))
    year = int(year_match.group(0)) if year_match else None
    venue_value = verified.get("venue") if verified_record else claimed.get("venue") or raw.get("venue") or supplement.get("venue")
    if isinstance(venue_value, dict):
        venue_value = venue_value.get("short_name") or venue_value.get("name") or venue_value.get("raw") or ""
    venue = normalize_venue(str(venue_value or ""))
    doi = normalize_doi(verified.get("doi") if verified_record else raw.get("doi"), raw.get("identifier"), supplement.get("doi"))
    official_url = str(
        resolved.get("registry_record_url")
        or verified.get("source_url")
        or raw.get("registry_record_url")
        or ""
    )
    normalized = {
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "doi": doi,
        "canonical_url": str(raw.get("canonical_url") or raw.get("url") or ""),
        "pdf_url": str(raw.get("pdf_url") or ""),
        "title_source": title_source,
        "authors_source": authors_source,
    }
    identity_input = {
        **raw,
        **resolved,
        "document_type": "paper",
        "document_claimed_metadata": claimed,
        "unverified_supplement": supplement,
    }
    if verified_record:
        identity_input["verified_academic_metadata"] = verified
    gate = assess_academic_identity(identity_input)
    verified_identity = {
        "status": "verified" if gate.get("official_record") else "unverified",
        "official_record_url": official_url,
        "registry_name": str(resolved.get("registry_name") or raw.get("registry_name") or ""),
        "metadata": verified if verified_record else {},
        "academic_gate": gate,
    }
    status = "completed_with_fallback" if fallback_reasons else "completed"
    return {
        "raw_metadata": raw,
        "normalized_metadata": normalized,
        "verified_identity": verified_identity,
        "candidate_boundaries": candidates,
        "schema_version": METADATA_SCHEMA_VERSION,
        "parser_version": METADATA_PARSER_VERSION,
        "strategy_version": METADATA_STRATEGY_VERSION,
        "execution_status": status,
        "fallback_reasons": fallback_reasons,
        "normalized_at": datetime.now(timezone.utc).isoformat(),
    }


def title_fingerprint(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def canonical_identity_keys(metadata: dict | None) -> set[str]:
    metadata = metadata or {}
    keys: set[str] = set()
    doi = normalize_doi(metadata.get("doi"))
    if doi:
        keys.add(f"doi:{doi}")
    for raw_url in (
        metadata.get("official_record_url"), metadata.get("registry_record_url"),
        metadata.get("source_url"), metadata.get("resolved_source_url"), metadata.get("canonical_url"),
        metadata.get("pdf_url"), metadata.get("metadata_url"),
    ):
        url = str(raw_url or "").strip().rstrip("/")
        if not url:
            continue
        keys.add(f"url:{url.casefold()}")
        arxiv = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/]+)", url, re.IGNORECASE)
        if arxiv:
            keys.add(f"arxiv:{arxiv.group(1).removesuffix('.pdf').casefold()}")
        openreview = re.search(r"openreview\.net/forum\?id=([^&#]+)", url, re.IGNORECASE)
        if openreview:
            keys.add(f"openreview:{openreview.group(1).casefold()}")
    fingerprint = title_fingerprint(metadata.get("title"))
    if fingerprint:
        keys.add(f"title:{fingerprint}")
    return keys
