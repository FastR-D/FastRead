from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse


TOP_SECURITY_VENUES = {
    "ieee_sp": {
        "name": "IEEE Symposium on Security and Privacy",
        "short_name": "IEEE S&P",
        "patterns": (
            r"\bieee\s+(?:symposium\s+on\s+)?security\s*(?:and|&)\s*privacy\b",
            r"\bieee\s+s\s*&\s*p\b",
            r"\boakland\s+(?:conference|symposium)\b",
        ),
    },
    "usenix_security": {
        "name": "USENIX Security Symposium",
        "short_name": "USENIX Security",
        "patterns": (r"\busenix\s+(?:security(?:\s+symposium)?)\b",),
    },
    "acm_ccs": {
        "name": "ACM Conference on Computer and Communications Security",
        "short_name": "ACM CCS",
        "patterns": (
            r"\bacm\s+(?:conference\s+on\s+)?computer\s+and\s+communications\s+security\b",
            r"\bacm\s+ccs\b",
        ),
    },
    "ndss": {
        "name": "Network and Distributed System Security Symposium",
        "short_name": "NDSS",
        "patterns": (
            r"\bnetwork\s+and\s+distributed\s+system\s+security(?:\s+symposium)?\b",
            r"\bndss(?:\s+symposium)?\b",
        ),
    },
}

SYSTEMS_VENUES = {
    "usenix_osdi": {
        "name": "USENIX Symposium on Operating Systems Design and Implementation",
        "short_name": "OSDI",
        "patterns": (
            r"\b(?:usenix\s+)?(?:symposium\s+on\s+)?operating\s+systems\s+design\s+and\s+implementation\b",
            r"\bosdi\b",
        ),
    },
    "acm_sosp": {
        "name": "ACM Symposium on Operating Systems Principles",
        "short_name": "SOSP",
        "patterns": (
            r"\b(?:acm\s+)?symposium\s+on\s+operating\s+systems\s+principles\b",
            r"\bsosp\b",
        ),
    },
    "asplos": {
        "name": "ACM International Conference on Architectural Support for Programming Languages and Operating Systems",
        "short_name": "ASPLOS",
        "patterns": (
            r"\barchitectural\s+support\s+for\s+programming\s+languages\s+and\s+operating\s+systems\b",
            r"\basplos\b",
        ),
    },
    "eurosys": {
        "name": "European Conference on Computer Systems",
        "short_name": "EuroSys",
        "patterns": (
            r"\beuropean\s+conference\s+on\s+computer\s+systems\b",
            r"\beurosys\b",
        ),
    },
    "usenix_atc": {
        "name": "USENIX Annual Technical Conference",
        "short_name": "USENIX ATC",
        "patterns": (
            r"\busenix\s+annual\s+technical\s+conference\b",
            r"\busenix\s+atc\b",
            r"\batc\s*'?\d{2}\b",
        ),
    },
    "sigcomm": {
        "name": "ACM Special Interest Group on Data Communication",
        "short_name": "SIGCOMM",
        "patterns": (
            r"\b(?:acm\s+)?sigcomm\b",
            r"\bspecial\s+interest\s+group\s+on\s+data\s+communication\b",
        ),
    },
    "nsdi": {
        "name": "USENIX Symposium on Networked Systems Design and Implementation",
        "short_name": "NSDI",
        "patterns": (
            r"\b(?:usenix\s+)?(?:symposium\s+on\s+)?networked\s+systems\s+design\s+and\s+implementation\b",
            r"\bnsdi\b",
        ),
    },
    "fast": {
        "name": "USENIX Conference on File and Storage Technologies",
        "short_name": "USENIX FAST",
        "patterns": (
            r"\b(?:usenix\s+)?conference\s+on\s+file\s+and\s+storage\s+technologies\b",
            r"\bfast\s*'?\d{2}\b",
        ),
    },
}


def _configured_venue_ids(env_name: str, default_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Read a comma-separated venue-id allowlist from the environment."""
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default_ids
    requested = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return requested or default_ids


def security_venue_ids() -> tuple[str, ...]:
    """The security "big four" — overridable via PAPER_SEARCH_SECURITY_VENUES."""
    return _configured_venue_ids(
        "PAPER_SEARCH_SECURITY_VENUES", tuple(TOP_SECURITY_VENUES.keys())
    )


def systems_venue_ids() -> tuple[str, ...]:
    """Systems top conferences — overridable via PAPER_SEARCH_SYSTEMS_VENUES."""
    return _configured_venue_ids(
        "PAPER_SEARCH_SYSTEMS_VENUES", tuple(SYSTEMS_VENUES.keys())
    )


def allowed_venue_catalog() -> dict[str, dict]:
    """Merged {venue_id: metadata} for the configured security + systems allowlist."""
    catalog: dict[str, dict] = {}
    for venue_id in security_venue_ids():
        if venue_id in TOP_SECURITY_VENUES:
            catalog[venue_id] = {**TOP_SECURITY_VENUES[venue_id], "track": "security"}
    for venue_id in systems_venue_ids():
        if venue_id in SYSTEMS_VENUES:
            catalog[venue_id] = {**SYSTEMS_VENUES[venue_id], "track": "systems"}
    return catalog


def match_allowed_venue(*values: str | None) -> dict:
    """Match any free-text venue hint against the configured allowlist.

    Returns ``{"id", "name", "short_name", "track", "raw"}`` on a hit, else an
    empty-id dict. Used by paper search to keep results inside the big-four +
    systems-conference corpus.
    """
    catalog = allowed_venue_catalog()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            continue
        lowered = text.lower()
        for venue_id, metadata in catalog.items():
            if any(re.search(p, lowered, re.IGNORECASE) for p in metadata["patterns"]):
                return {
                    "id": venue_id,
                    "name": metadata["name"],
                    "short_name": metadata["short_name"],
                    "track": metadata["track"],
                    "raw": text,
                }
    return {"id": "", "name": "", "short_name": "", "track": "", "raw": ""}


OFFICIAL_ACADEMIC_HOSTS = {
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "usenix.org",
    "www.usenix.org",
    "ndss-symposium.org",
    "www.ndss-symposium.org",
    "doi.org",
}

PREPRINT_HOST_HINTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "ssrn.com")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def normalize_venue(value: str | None) -> dict:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    for venue_id, metadata in TOP_SECURITY_VENUES.items():
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in metadata["patterns"]):
            return {
                "id": venue_id,
                "name": metadata["name"],
                "short_name": metadata["short_name"],
                "raw": text,
            }
    return {"id": "", "name": text, "short_name": text, "raw": text}


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


def assess_academic_identity(metadata: dict | None) -> dict:
    metadata = metadata or {}
    has_fetch_provenance = (
        "official_record_verified" in metadata
        or "verified_academic_metadata" in metadata
    )
    verified_metadata = (
        metadata.get("verified_academic_metadata")
        if metadata.get("official_record_verified") is True
        and isinstance(metadata.get("verified_academic_metadata"), dict)
        else {}
    )
    identity_metadata = verified_metadata if has_fetch_provenance else metadata
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
        str(metadata.get(key) or "")
        for key in ("publication_status", "title", "notice", "status")
    ).lower()

    is_withdrawn = any(token in status_text for token in ("withdrawn", "撤回"))
    is_retracted = any(token in status_text for token in ("retracted", "撤稿")) or is_withdrawn
    is_preprint = any(hint in domain for hint in PREPRINT_HOST_HINTS) or "preprint" in status_text or "预印本" in status_text
    official_host_match = domain in OFFICIAL_ACADEMIC_HOSTS
    official_record = bool(
        official_host_match
        and metadata.get("official_record_verified") is True
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
    identity_complete = bool(title and authors and year and official_record)
    is_top4_security = bool(venue["id"])
    gate_passed = bool(identity_complete and is_top4_security and not is_retracted and not is_preprint)

    if gate_passed:
        level = "A1"
        label = "四大安全顶会正式论文，身份完整"
    elif identity_complete and not is_retracted and not is_preprint:
        level = "A2"
        label = "正式论文，身份完整但不属于限定四大安全顶会"
    elif is_preprint and title and authors and year:
        level = "B1"
        label = "预印本，身份可识别但未经限定顶会正式发表 Gate"
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
            warnings.append("missing_official_record_or_doi")
            warnings.append("missing_verified_official_record")
        if not is_top4_security:
            warnings.append("not_top4_security_venue")
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
        "identity_complete": identity_complete,
        "is_top4_security": is_top4_security,
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
        "official_host_match": official_host_match,
        "verified_metadata_used": bool(verified_metadata),
        "has_academic_signal": has_academic_signal,
        "warnings": warnings,
    }
