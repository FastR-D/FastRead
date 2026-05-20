from __future__ import annotations

from app.services.verification.constants import GENERIC_SEARCH_TERMS
from app.services.verification.numeric_evidence import (
    has_egg_context,
    has_protein_context,
    is_scientific_claim,
    score_numeric_evidence,
)
from app.services.verification.query_builder import domain_terms_for_claim
from app.services.verification.text_utils import is_low_value_result, tokenize


def result_relevance(claim: str, result: dict) -> dict:
    claim_tokens = tokenize(claim)
    result_text = f"{result.get('title', '')} {result.get('snippet', '')}"
    result_tokens = tokenize(result_text)
    meaningful_claim_tokens = claim_tokens - GENERIC_SEARCH_TERMS
    overlap = meaningful_claim_tokens & result_tokens
    required_terms = domain_terms_for_claim(claim)
    required_tokens = tokenize(" ".join(required_terms))
    required_hit = bool(required_tokens & result_tokens) if required_tokens else True
    coverage = round(len(overlap) / max(len(meaningful_claim_tokens), 1), 2)
    scientific_hit = (
        is_scientific_claim(claim)
        and (not has_protein_context(claim) or has_protein_context(result_text))
        and (not has_egg_context(claim) or has_egg_context(result_text))
    )
    relevant = required_hit and (
        coverage >= 0.18
        or len(overlap) >= 4
        or (scientific_hit and (result.get("trusted") or len(overlap) >= 1))
    )
    return {
        "coverage": coverage,
        "overlap": len(overlap),
        "required_hit": required_hit,
        "relevant": relevant and not is_low_value_result(result, claim),
    }


def filter_relevant_results(claim: str, results: list[dict]) -> list[dict]:
    filtered = []
    for result in results:
        relevance = result_relevance(claim, result)
        if not relevance["relevant"]:
            continue
        filtered.append({
            **result,
            "relevance": {
                "coverage": relevance["coverage"],
                "overlap": relevance["overlap"],
            },
        })
    return filtered


def score_results(claim: str, results: list[dict]) -> dict:
    claim_tokens = tokenize(claim) - GENERIC_SEARCH_TERMS
    if not claim_tokens:
        return {
            "coverage": 0,
            "trusted_count": 0,
            "top_overlap": 0,
            **score_numeric_evidence(claim, results),
        }

    top_overlap = 0
    trusted_count = 0
    coverage_hits = set()
    for result in results:
        tokens = tokenize(f"{result.get('title', '')} {result.get('snippet', '')}")
        overlap = claim_tokens & tokens
        if result.get("trusted"):
            trusted_count += 1
        if overlap:
            coverage_hits |= overlap
            top_overlap = max(top_overlap, len(overlap))

    return {
        "coverage": round(len(coverage_hits) / max(len(claim_tokens), 1), 2),
        "trusted_count": trusted_count,
        "top_overlap": top_overlap,
        **score_numeric_evidence(claim, results),
    }
