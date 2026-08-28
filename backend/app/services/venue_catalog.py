from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VenueDefinition:
    id: str
    name: str
    short_name: str
    track: str
    patterns: tuple[str, ...]


VENUES: tuple[VenueDefinition, ...] = (
    VenueDefinition("ieee_sp", "IEEE Symposium on Security and Privacy", "IEEE S&P", "security", (r"\bieee\s+(?:symposium\s+on\s+)?security\s*(?:and|&)\s*privacy\b", r"\bieee\s+s\s*&\s*p\b", r"\boakland\s+(?:conference|symposium)\b")),
    VenueDefinition("usenix_security", "USENIX Security Symposium", "USENIX Security", "security", (r"\busenix\s+(?:security(?:\s+symposium)?)\b",)),
    VenueDefinition("acm_ccs", "ACM Conference on Computer and Communications Security", "ACM CCS", "security", (r"\bacm\s+(?:conference\s+on\s+)?computer\s+and\s+communications\s+security\b", r"\bacm\s+ccs\b")),
    VenueDefinition("ndss", "Network and Distributed System Security Symposium", "NDSS", "security", (r"\bnetwork\s+and\s+distributed\s+system\s+security(?:\s+symposium)?\b", r"\bndss(?:\s+symposium)?\b")),
    VenueDefinition("usenix_osdi", "USENIX Symposium on Operating Systems Design and Implementation", "OSDI", "systems", (r"\boperating\s+systems\s+design\s+and\s+implementation\b", r"\bosdi\b")),
    VenueDefinition("acm_sosp", "ACM Symposium on Operating Systems Principles", "SOSP", "systems", (r"\bsymposium\s+on\s+operating\s+systems\s+principles\b", r"\bsosp\b")),
    VenueDefinition("asplos", "ACM International Conference on Architectural Support for Programming Languages and Operating Systems", "ASPLOS", "systems", (r"\barchitectural\s+support\s+for\s+programming\s+languages\s+and\s+operating\s+systems\b", r"\basplos\b")),
    VenueDefinition("eurosys", "European Conference on Computer Systems", "EuroSys", "systems", (r"\beuropean\s+conference\s+on\s+computer\s+systems\b", r"\beurosys\b")),
    VenueDefinition("usenix_atc", "USENIX Annual Technical Conference", "USENIX ATC", "systems", (r"\busenix\s+annual\s+technical\s+conference\b", r"\busenix\s+atc\b")),
    VenueDefinition("sigcomm", "ACM SIGCOMM Conference", "SIGCOMM", "systems", (r"\b(?:acm\s+)?sigcomm\b",)),
    VenueDefinition("nsdi", "USENIX Symposium on Networked Systems Design and Implementation", "NSDI", "systems", (r"\bnetworked\s+systems\s+design\s+and\s+implementation\b", r"\bnsdi\b")),
    VenueDefinition("fast", "USENIX Conference on File and Storage Technologies", "USENIX FAST", "systems", (r"\bconference\s+on\s+file\s+and\s+storage\s+technologies\b", r"\busenix\s+fast\b")),
    VenueDefinition("iclr", "International Conference on Learning Representations", "ICLR", "ai", (r"\binternational\s+conference\s+on\s+learning\s+representations\b", r"\biclr\b")),
    VenueDefinition("icml", "International Conference on Machine Learning", "ICML", "ai", (r"\binternational\s+conference\s+on\s+machine\s+learning\b", r"\bicml\b")),
    VenueDefinition("aaai", "AAAI Conference on Artificial Intelligence", "AAAI", "ai", (r"\baaai\s+conference\s+on\s+artificial\s+intelligence\b", r"\baaai\b")),
    VenueDefinition("neurips", "Conference on Neural Information Processing Systems", "NeurIPS", "ai", (r"\b(?:conference\s+on\s+)?neural\s+information\s+processing\s+systems\b", r"\bneurips\b", r"\bnips\b")),
    VenueDefinition("acl", "Annual Meeting of the Association for Computational Linguistics", "ACL", "ai", (r"\bannual\s+meeting\s+of\s+the\s+association\s+for\s+computational\s+linguistics\b", r"\bacl\b")),
)


_BY_ID = {venue.id: venue for venue in VENUES}


def _configured_ids(track: str) -> set[str]:
    defaults = [venue.id for venue in VENUES if venue.track == track]
    raw = os.getenv(f"PAPER_SEARCH_{track.upper()}_VENUES", "").strip()
    return set(item.strip().lower() for item in raw.split(",") if item.strip()) if raw else set(defaults)


def venue_ids(track: str) -> tuple[str, ...]:
    enabled = _configured_ids(track)
    return tuple(venue.id for venue in VENUES if venue.track == track and venue.id in enabled)


def security_venue_ids() -> tuple[str, ...]:
    return venue_ids("security")


def systems_venue_ids() -> tuple[str, ...]:
    return venue_ids("systems")


def ai_venue_ids() -> tuple[str, ...]:
    return venue_ids("ai")


def allowed_venue_catalog() -> dict[str, dict]:
    enabled = {venue_id for track in ("security", "systems", "ai") for venue_id in venue_ids(track)}
    return {
        venue.id: {
            "name": venue.name,
            "short_name": venue.short_name,
            "track": venue.track,
            "patterns": venue.patterns,
        }
        for venue in VENUES
        if venue.id in enabled
    }


def match_allowed_venue(*values: str | None) -> dict:
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            continue
        for venue_id, metadata in allowed_venue_catalog().items():
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in metadata["patterns"]):
                return {"id": venue_id, **metadata, "raw": text}
    return {"id": "", "name": "", "short_name": "", "track": "", "raw": ""}
