from __future__ import annotations

import re

from app.services.verification.constants import (
    GENERIC_SEARCH_TERMS,
    NUMERIC_OPERATOR_WORDS,
    SCIENTIFIC_CLAIM_HINTS,
)
from app.services.verification.text_utils import domain, tokenize


def normalize_number(value: str) -> float | None:
    try:
        return float(str(value or "").replace(",", ""))
    except Exception:
        return None


def numeric_op_pattern() -> str:
    words = sorted(NUMERIC_OPERATOR_WORDS, key=len, reverse=True)
    return "|".join(re.escape(word) for word in words)


def extract_numeric_mentions(text: str, include_operator: bool = True) -> list[dict]:
    if not text:
        return []
    op_pattern = numeric_op_pattern()
    pattern = re.compile(
        rf"(?P<prefix>{op_pattern})?\s*"
        r"(?P<number>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
        r"(?P<unit>%|种|个|项|倍|元|分钟|小时|天|年|proteins?|protein entries|entries)?\s*"
        rf"(?P<suffix>{op_pattern})?",
        re.I,
    )
    mentions = []
    for match in pattern.finditer(text):
        value = normalize_number(match.group("number"))
        if value is None:
            continue
        start, end = match.span()
        context = text[max(0, start - 28): min(len(text), end + 28)]
        raw_op = (match.group("prefix") or match.group("suffix") or "").strip().lower()
        op = NUMERIC_OPERATOR_WORDS.get(raw_op, "eq") if include_operator else "eq"
        unit = (match.group("unit") or "").strip().lower()
        mentions.append({
            "value": value,
            "op": op,
            "unit": unit,
            "context": context,
            "raw": match.group(0).strip(),
        })
    return mentions


def extract_numeric_constraints(claim: str) -> list[dict]:
    mentions = extract_numeric_mentions(claim, include_operator=True)
    constraints = []
    for mention in mentions:
        context = mention.get("context") or ""
        value = float(mention["value"])
        if 1800 <= value <= 2099 and re.search(r"年|year", context, re.I):
            continue
        constraints.append(mention)
    return constraints


def is_scientific_claim(text: str) -> bool:
    lower = (text or "").lower()
    return any(hint in lower for hint in SCIENTIFIC_CLAIM_HINTS)


def has_protein_context(text: str) -> bool:
    lower = (text or "").lower()
    return any(hint in lower for hint in ("蛋白", "protein", "proteome", "proteomic"))


def has_egg_context(text: str) -> bool:
    lower = (text or "").lower()
    return any(hint in lower for hint in ("鸡蛋", "蛋清", "蛋黄", "egg", "yolk", "albumen"))


def numeric_context_related(claim_mention: dict, source_mention: dict) -> bool:
    claim_context = claim_mention.get("context") or ""
    source_context = source_mention.get("context") or ""
    if has_protein_context(claim_context) and has_protein_context(source_context):
        return True
    if has_egg_context(claim_context) and has_egg_context(source_context):
        return True
    claim_tokens = tokenize(claim_context) - GENERIC_SEARCH_TERMS
    source_tokens = tokenize(source_context) - GENERIC_SEARCH_TERMS
    return bool(claim_tokens & source_tokens)


def numeric_supports(claim_mention: dict, source_mention: dict) -> bool:
    claim_value = float(claim_mention["value"])
    source_value = float(source_mention["value"])
    claim_op = claim_mention.get("op") or "eq"
    source_op = source_mention.get("op") or "eq"
    tolerance = max(abs(claim_value) * 0.02, 1.0)

    if claim_op in {"gt", "gte"}:
        if source_op in {"gt", "gte"} and source_value >= claim_value - tolerance:
            return True
        return source_value >= claim_value - tolerance
    if claim_op in {"lt", "lte"}:
        if source_op in {"lt", "lte"} and source_value <= claim_value + tolerance:
            return True
        return source_value <= claim_value + tolerance
    if claim_op == "approx":
        return abs(source_value - claim_value) <= max(abs(claim_value) * 0.15, 2.0)
    return abs(source_value - claim_value) <= tolerance


def numeric_conflicts(claim_mention: dict, source_mention: dict) -> bool:
    claim_value = float(claim_mention["value"])
    source_value = float(source_mention["value"])
    claim_op = claim_mention.get("op") or "eq"
    source_op = source_mention.get("op") or "eq"
    tolerance = max(abs(claim_value) * 0.02, 2.0)

    if claim_op in {"gt", "gte"}:
        return source_op in {"eq", "approx", "lt", "lte"} and source_value < claim_value - tolerance
    if claim_op in {"lt", "lte"}:
        return source_op in {"eq", "approx", "gt", "gte"} and source_value > claim_value + tolerance
    if claim_op == "approx":
        return abs(source_value - claim_value) > max(abs(claim_value) * 0.25, 3.0)
    return abs(source_value - claim_value) > tolerance


def score_numeric_evidence(claim: str, results: list[dict]) -> dict:
    constraints = extract_numeric_constraints(claim)
    if not constraints:
        return {
            "numeric_claim": False,
            "numeric_match_count": 0,
            "numeric_conflict_count": 0,
            "numeric_unmatched_count": 0,
            "numeric_evidence": [],
        }

    match_count = 0
    conflict_count = 0
    comparable_count = 0
    evidence = []
    for constraint in constraints:
        for result in results:
            source_text = f"{result.get('title', '')} {result.get('snippet', '')}"
            for mention in extract_numeric_mentions(source_text, include_operator=True):
                value = float(mention["value"])
                if 1800 <= value <= 2099 and re.search(r"年|year", mention.get("context", ""), re.I):
                    continue
                if not numeric_context_related(constraint, mention):
                    continue
                comparable_count += 1
                item = {
                    "claim_number": constraint.get("raw"),
                    "source_number": mention.get("raw"),
                    "source_title": result.get("title", "")[:120],
                    "source_domain": result.get("domain") or domain(result.get("url") or ""),
                }
                if numeric_supports(constraint, mention):
                    match_count += 1
                    evidence.append({**item, "relation": "support"})
                elif numeric_conflicts(constraint, mention):
                    conflict_count += 1
                    evidence.append({**item, "relation": "conflict"})

    return {
        "numeric_claim": True,
        "numeric_match_count": match_count,
        "numeric_conflict_count": conflict_count,
        "numeric_unmatched_count": max(len(constraints) - match_count, 0),
        "numeric_comparable_count": comparable_count,
        "numeric_evidence": evidence[:5],
    }
