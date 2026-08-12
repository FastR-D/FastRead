from __future__ import annotations

import hashlib
import re

from app.services.verification import numeric_evidence
from app.services.verification.constants import GENERIC_SEARCH_TERMS
from app.services.verification.schemas import VerificationEvidence
from app.services.verification.text_utils import tokenize


def _sentences(text: str) -> list[tuple[int, int, str]]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    chunks = []
    start = 0
    for match in re.finditer(r"[。！？!?；;]+\s*|(?<=\.)\s+(?=[A-Z0-9])", cleaned):
        end = match.end()
        sentence = cleaned[start:end].strip()
        if sentence:
            chunks.append((start, end, sentence))
        start = end
    tail = cleaned[start:].strip()
    if tail:
        chunks.append((start, len(cleaned), tail))
    return chunks


def _best_passages(claim: str, text: str, limit: int = 5) -> list[tuple[int, int, str, int]]:
    claim_tokens = tokenize(claim) - GENERIC_SEARCH_TERMS
    scored = []
    for start, end, sentence in _sentences(text):
        tokens = tokenize(sentence)
        overlap = len(claim_tokens & tokens)
        numeric_bonus = 2 if numeric_evidence.extract_numeric_mentions(sentence) else 0
        if overlap or numeric_bonus:
            scored.append((overlap + numeric_bonus, start, end, sentence))
    scored.sort(reverse=True)
    return [(start, end, sentence[:800], score) for score, start, end, sentence in scored[:limit]]


def _page_offsets(start: int, end: int, source: dict) -> dict[str, int]:
    offsets = {"start": start, "end": end}
    spans = source.get("page_spans") or []
    matched_pages = [
        int(span.get("page"))
        for span in spans
        if span.get("page") is not None and start < int(span.get("end", 0)) and end > int(span.get("start", 0))
    ]
    if matched_pages:
        offsets["page_start"] = min(matched_pages)
        offsets["page_end"] = max(matched_pages)
    return offsets


def evidence_id_for(source: dict, stance: str, start: int, end: int, passage: str) -> str:
    source_key = source.get("source_id") or source.get("url") or ""
    passage_hash = hashlib.sha1((passage or "").encode("utf-8", errors="ignore")).hexdigest()[:10]
    stable = f"{source_key}|{stance}|{start}|{end}|{passage_hash}"
    digest = hashlib.sha1(stable.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"ev-{digest}"


def _numeric_stance(claim: str, passage: str) -> tuple[str | None, str, str]:
    constraints = numeric_evidence.extract_numeric_constraints(claim)
    if not constraints:
        return None, "", ""
    saw_number = False
    for constraint in constraints:
        for mention in numeric_evidence.extract_numeric_mentions(passage, include_operator=True):
            saw_number = True
            value = float(mention["value"])
            if 1800 <= value <= 2099 and re.search(r"年|year", mention.get("context", ""), re.I):
                continue
            if not numeric_evidence.numeric_context_related(constraint, mention):
                continue
            if numeric_evidence.numeric_supports(constraint, mention):
                return "support", mention.get("raw") or "", mention.get("unit") or ""
            if numeric_evidence.numeric_conflicts(constraint, mention):
                return "refute", mention.get("raw") or "", mention.get("unit") or ""
    return ("context" if saw_number else None), "", ""


def _classification_stance(claim: str, passage: str) -> tuple[str | None, str, str]:
    claim_group = _iarc_group(claim)
    if not claim_group:
        return None, "", ""
    passage_group = _iarc_group(passage)
    if not passage_group:
        return None, "", ""
    if claim_group == passage_group:
        return "support", passage_group, "IARC group"
    return "refute", passage_group, "IARC group"


def _iarc_group(text: str) -> str:
    lower = (text or "").lower()
    if "iarc" not in lower and "致癌" not in text and "carcinogenic" not in lower:
        return ""
    patterns = (
        r"iarc\s*(?:group\s*)?([12][a-b]?|3|4)",
        r"group\s*([12][a-b]?|3|4)",
        r"([12][a-b]?|3|4)\s*类",
    )
    for pattern in patterns:
        match = re.search(pattern, lower, re.I)
        if match:
            return match.group(1).lower()
    if "确定致癌" in text or "carcinogenic to humans" in lower:
        return "1"
    if "可能对人类致癌" in text or "possibly carcinogenic" in lower:
        return "2b"
    return ""


def extract_evidence_for_claim(claim: str, source: dict, text: str) -> list[dict]:
    if not claim or not text:
        return []
    claim_tokens = tokenize(claim) - GENERIC_SEARCH_TERMS
    extracted = []
    for start, end, passage, score in _best_passages(claim, text, limit=5):
        stance, exact_value, unit = _classification_stance(claim, passage)
        extraction_method = "body_classification_rules" if stance else "body_overlap_rules"
        if stance is None:
            stance, exact_value, unit = _numeric_stance(claim, passage)
            if exact_value:
                extraction_method = "body_numeric_rules"
        if stance is None:
            coverage = len(claim_tokens & tokenize(passage)) / max(len(claim_tokens), 1)
            stance = "support" if coverage >= 0.5 and source.get("trust_tier") in {"A", "B"} else "context"
        confidence = min(95, max(35, score * 12 + (20 if source.get("trust_tier") in {"A", "B"} else 0)))
        extracted.append(
            VerificationEvidence(
                source_url=source.get("url") or "",
                evidence_id=evidence_id_for(source, stance, start, end, passage),
                passage=passage,
                stance=stance,
                claim_element="numeric" if exact_value else "overall",
                exact_value=exact_value,
                unit=unit,
                page_offsets=_page_offsets(start, end, source),
                confidence=confidence,
                extraction_method=extraction_method,
            )
        )
    return [item.__dict__ for item in extracted]


def evidence_counts(evidence: list[dict], sources_by_url: dict[str, dict]) -> dict:
    high_support_groups = set()
    high_refute_groups = set()
    support = refute = context = 0
    for item in evidence:
        source = sources_by_url.get(item.get("source_url") or "") or {}
        group = source.get("independence_group") or source.get("domain") or item.get("source_url")
        source_risks = set(source.get("risk_flags") or [])
        disqualifying_risks = {
            "blocked_domain",
            "canonical_anomaly",
            "fake_authority",
            "missing_source_identity",
            "prompt_injection",
            "redirect_anomaly",
            "retracted_or_withdrawn",
        }
        high_quality = (
            source.get("trust_tier") in {"A", "B"}
            and source.get("fetch_status") in {"ok", "pdf_ok"}
            and not (source_risks & disqualifying_risks)
        )
        if item.get("stance") == "support":
            support += 1
            if high_quality:
                high_support_groups.add(group)
        elif item.get("stance") == "refute":
            refute += 1
            if high_quality:
                high_refute_groups.add(group)
        else:
            context += 1
    return {
        "support": support,
        "refute": refute,
        "context": context,
        "high_support_independent": len(high_support_groups),
        "high_refute_independent": len(high_refute_groups),
    }
