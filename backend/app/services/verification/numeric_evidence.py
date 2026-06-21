from __future__ import annotations

import re

from app.services.verification.constants import (
    GENERIC_SEARCH_TERMS,
    NUMERIC_OPERATOR_WORDS,
    SCIENTIFIC_CLAIM_HINTS,
)
from app.services.verification.text_utils import domain, tokenize


UNIT_PATTERN = (
    r"billion\s+people|million\s+people|billion|million|"
    r"亿人|万人|人|亿|万|"
    r"mg/kg|mg\/kg|%|种|个|项|倍|元|分钟|小时|天|年|proteins?|protein entries|entries"
)


def normalize_number(value: str) -> float | None:
    try:
        return float(str(value or "").replace(",", ""))
    except Exception:
        return None


def normalize_number_with_unit(value: float, unit: str) -> float:
    normalized_unit = (unit or "").strip().lower()
    if normalized_unit in {"亿", "亿人"}:
        return value * 100_000_000
    if normalized_unit in {"万", "万人"}:
        return value * 10_000
    if normalized_unit in {"billion", "billion people"}:
        return value * 1_000_000_000
    if normalized_unit in {"million", "million people"}:
        return value * 1_000_000
    return value


def numeric_op_pattern() -> str:
    words = sorted(NUMERIC_OPERATOR_WORDS, key=len, reverse=True)
    return "|".join(re.escape(word) for word in words)


def extract_numeric_mentions(text: str, include_operator: bool = True) -> list[dict]:
    if not text:
        return []
    mentions = _extract_numeric_ranges(text, include_operator=include_operator)
    op_pattern = numeric_op_pattern()
    pattern = re.compile(
        rf"(?P<prefix>{op_pattern})?\s*"
        r"(?P<number>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
        rf"(?P<unit>{UNIT_PATTERN})?\s*"
        rf"(?P<suffix>{op_pattern})?",
        re.I,
    )
    covered_spans = [item.get("span") for item in mentions if item.get("span")]
    for match in pattern.finditer(text):
        if any(match.start() < span[1] and match.end() > span[0] for span in covered_spans):
            continue
        value = normalize_number(match.group("number"))
        if value is None:
            continue
        start, end = match.span()
        context = text[max(0, start - 52): min(len(text), end + 52)]
        raw_op = (match.group("prefix") or match.group("suffix") or "").strip().lower()
        op = NUMERIC_OPERATOR_WORDS.get(raw_op, "eq") if include_operator else "eq"
        unit = (match.group("unit") or "").strip().lower()
        if _is_non_factual_number(match.group(0), value, unit, context):
            continue
        normalized_value = normalize_number_with_unit(value, unit)
        mentions.append({
            "value": normalized_value,
            "raw_value": value,
            "op": op,
            "unit": unit,
            "context": context,
            "raw": match.group(0).strip(),
            "kind": numeric_kind(unit, context),
            "span": (start, end),
        })
    return mentions


def _extract_numeric_ranges(text: str, include_operator: bool = True) -> list[dict]:
    pattern = re.compile(
        r"(?P<low>\d+(?:\.\d+)?)\s*[–-]\s*(?P<high>\d+(?:\.\d+)?)\s*"
        rf"(?P<unit>{UNIT_PATTERN})?",
        re.I,
    )
    mentions = []
    for match in pattern.finditer(text):
        low = normalize_number(match.group("low"))
        high = normalize_number(match.group("high"))
        if low is None or high is None:
            continue
        start, end = match.span()
        context = text[max(0, start - 52): min(len(text), end + 52)]
        unit = (match.group("unit") or "").strip().lower()
        if _is_non_factual_number(match.group(0), high, unit, context):
            continue
        normalized_low = normalize_number_with_unit(low, unit)
        normalized_high = normalize_number_with_unit(high, unit)
        mentions.append(
            {
                "value": normalized_high,
                "raw_value": high,
                "low_value": normalized_low,
                "high_value": normalized_high,
                "raw_low_value": low,
                "raw_high_value": high,
                "op": "range" if include_operator else "eq",
                "unit": unit,
                "context": context,
                "raw": match.group(0).strip(),
                "kind": numeric_kind(unit, context),
                "span": (start, end),
            }
        )
    return mentions


def extract_numeric_constraints(claim: str) -> list[dict]:
    mentions = extract_numeric_mentions(claim, include_operator=True)
    constraints = []
    for mention in mentions:
        context = mention.get("context") or ""
        value = float(mention["value"])
        if 1800 <= value <= 2099 and re.search(r"年|year", context, re.I):
            continue
        if mention.get("kind") in {"year", "classification", "contact", "date"}:
            continue
        constraints.append(mention)
    return constraints


def _is_non_factual_number(raw: str, value: float, unit: str, context: str) -> bool:
    raw_text = raw.strip()
    lower = (context or "").lower()
    left_context = lower.split(raw_text.lower(), 1)[0] if raw_text.lower() in lower else lower[:80]
    if 1800 <= value <= 2099 and re.search(r"年|year|published|released|updated", context, re.I):
        return True
    if re.search(r"\b(?:iarc\s*)?group\s*\d+[a-z]?\b|\b\d+[a-z]\b", lower, re.I):
        if "iarc" in lower or "carcinogenic" in lower or "致癌" in context:
            return True
    if re.search(r"(telephone|tel|mobile|fax|phone|email|media contacts?|communications officer|联系电话|电话|手机|邮编|媒体联络|新闻官|电子邮件)", lower, re.I):
        return True
    if re.search(r"(?:\+?\d[\s.-]*){6,}", raw_text):
        return True
    if re.search(r"(telephone|tel|mobile|fax|phone|email|电话|手机|联络|新闻官)$", left_context[-80:].strip(), re.I):
        return True
    if re.search(r"\b\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", lower, re.I):
        return True
    if unit == "天" and re.search(r"原标题|微信|公众号|加载|注册|登录|客户端", context):
        return True
    if not unit and value <= 31 and re.search(r"月|日|星期|january|february|march|april|june|july|august", lower):
        return True
    return False


def numeric_kind(unit: str, context: str) -> str:
    lower = (context or "").lower()
    unit = (unit or "").lower()
    if re.search(r"\b(?:iarc\s*)?group\s*\d+[a-z]?\b|\b\d+[a-z]\b", lower) and (
        "iarc" in lower or "carcinogenic" in lower or "致癌" in context
    ):
        return "classification"
    if unit in {"%", "倍"} or "percent" in lower:
        return "ratio"
    if unit in {"mg/kg", "mg", "kg"} or re.search(r"adi|acceptable daily intake|每日允许摄入量|摄入量", lower):
        return "dose"
    if re.search(r"kda|da\b|molecular weight|分子量", lower):
        return "molecular_weight"
    if has_protein_context(context) and re.search(r"entries|identified|proteins?|蛋白质|蛋白|种|个", lower):
        return "protein_count"
    if unit in {"人", "万人", "亿人", "万", "亿", "million", "billion", "million people", "billion people"} or re.search(
        r"population|people|居民|人口|人数", lower
    ):
        return "population_count"
    if unit in {"种", "个", "项", "entries", "protein entries"}:
        return "count"
    if unit in {"年"} or re.search(r"year|年", lower):
        return "year"
    if unit in {"分钟", "小时", "天"}:
        return "duration"
    return "number"


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
    claim_kind = claim_mention.get("kind") or numeric_kind(claim_mention.get("unit") or "", claim_context)
    source_kind = source_mention.get("kind") or numeric_kind(source_mention.get("unit") or "", source_context)
    if not numeric_kinds_comparable(claim_kind, source_kind):
        return False
    claim_unit = (claim_mention.get("unit") or "").lower()
    source_unit = (source_mention.get("unit") or "").lower()
    if claim_kind == "dose" and not (
        source_unit in {"mg/kg", "mg"} or re.search(r"adi|acceptable daily intake|每日允许摄入量|摄入量|body weight", source_context, re.I)
    ):
        return False
    if claim_unit and source_unit and claim_unit != source_unit:
        if not (
            {claim_kind, source_kind} <= {"protein_count", "count"}
            or {claim_kind, source_kind} <= {"population_count"}
        ):
            return False
    if claim_kind == source_kind == "population_count":
        return True
    if has_protein_context(claim_context) and has_protein_context(source_context):
        return True
    if has_egg_context(claim_context) and has_egg_context(source_context):
        return True
    claim_tokens = tokenize(claim_context) - GENERIC_SEARCH_TERMS
    source_tokens = tokenize(source_context) - GENERIC_SEARCH_TERMS
    return bool(claim_tokens & source_tokens)


def numeric_kinds_comparable(claim_kind: str, source_kind: str) -> bool:
    if claim_kind == source_kind:
        return True
    compatible = {
        frozenset({"protein_count", "count"}),
    }
    return frozenset({claim_kind, source_kind}) in compatible


def _has_approx_operator(*mentions: dict) -> bool:
    return any((mention.get("op") or "eq") == "approx" for mention in mentions)


def _approx_support_tolerance(value: float) -> float:
    return max(abs(value) * 0.15, 2.0)


def _approx_conflict_tolerance(value: float) -> float:
    return max(abs(value) * 0.25, 3.0)


def numeric_supports(claim_mention: dict, source_mention: dict) -> bool:
    claim_value = float(claim_mention["value"])
    source_value = float(source_mention["value"])
    claim_op = claim_mention.get("op") or "eq"
    source_op = source_mention.get("op") or "eq"
    approximate = _has_approx_operator(claim_mention, source_mention)
    tolerance = _approx_support_tolerance(claim_value) if approximate else max(abs(claim_value) * 0.02, 1.0)
    if source_op == "range":
        low = float(source_mention.get("low_value", source_value))
        high = float(source_mention.get("high_value", source_value))
        if claim_op in {"gt", "gte"}:
            return high >= claim_value - tolerance
        if claim_op in {"lt", "lte"}:
            return low <= claim_value + tolerance
        return low - tolerance <= claim_value <= high + tolerance or abs(high - claim_value) <= tolerance

    if claim_op in {"gt", "gte"}:
        if source_op in {"gt", "gte"} and source_value >= claim_value - tolerance:
            return True
        return source_value >= claim_value - tolerance
    if claim_op in {"lt", "lte"}:
        if source_op in {"lt", "lte"} and source_value <= claim_value + tolerance:
            return True
        return source_value <= claim_value + tolerance
    return abs(source_value - claim_value) <= tolerance


def numeric_conflicts(claim_mention: dict, source_mention: dict) -> bool:
    claim_value = float(claim_mention["value"])
    source_value = float(source_mention["value"])
    claim_op = claim_mention.get("op") or "eq"
    source_op = source_mention.get("op") or "eq"
    approximate = _has_approx_operator(claim_mention, source_mention)
    tolerance = _approx_conflict_tolerance(claim_value) if approximate else max(abs(claim_value) * 0.02, 2.0)
    if source_op == "range":
        low = float(source_mention.get("low_value", source_value))
        high = float(source_mention.get("high_value", source_value))
        if claim_op in {"gt", "gte"}:
            return high < claim_value - tolerance
        if claim_op in {"lt", "lte"}:
            return low > claim_value + tolerance
        return claim_value < low - tolerance or claim_value > high + tolerance

    if claim_op in {"gt", "gte"}:
        return source_op in {"eq", "approx", "lt", "lte"} and source_value < claim_value - tolerance
    if claim_op in {"lt", "lte"}:
        return source_op in {"eq", "approx", "gt", "gte"} and source_value > claim_value + tolerance
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
