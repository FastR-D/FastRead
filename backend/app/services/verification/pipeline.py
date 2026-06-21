from __future__ import annotations

import json
from hashlib import sha1
from typing import Any, Callable, Protocol

from app.services.verification import adjudication
from app.services.verification import claim_pipeline
from app.services.verification import evidence as evidence_service
from app.services.verification import fetching
from app.services.verification import query_builder
from app.services.verification import source_intel
from app.services.verification.constants import DEFAULT_MAX_RESULTS
from app.services.verification.schemas import (
    ClaimVerificationResult,
    to_plain_dict,
)


SearchFn = Callable[[list[str], int, str, list[str] | None], list[dict]]
FetchFn = Callable[[str, dict | None], dict]
StageCallback = Callable[[dict], None]


class VerificationCache(Protocol):
    def read(self, kind: str, key: str) -> dict | None:
        ...

    def write(self, kind: str, key: str, payload: dict) -> None:
        ...


def claim_id_for(text: str, index: int = 0) -> str:
    digest = sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"claim-{index + 1}-{digest}"


def cache_key_for(kind: str, payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = sha1(serialized.encode("utf-8", errors="ignore")).hexdigest()
    return f"{kind}-{digest}"


def _emit_stage(callback: StageCallback | None, payload: dict) -> None:
    if not callback:
        return
    callback(payload)


def _dominant_stance(evidence: list[dict], sources: list[dict]) -> str:
    source_by_url = {source.get("url") or "": source for source in sources}
    counts = {"support": 0, "refute": 0}
    for item in evidence:
        stance = item.get("stance")
        if stance not in counts:
            continue
        source = source_by_url.get(item.get("source_url") or "") or {}
        if source.get("trust_tier") in {"A", "B"}:
            counts[stance] += 1
    if counts["support"] > counts["refute"] and counts["support"] > 0:
        return "support"
    if counts["refute"] > counts["support"] and counts["refute"] > 0:
        return "refute"
    return "none"


def _geo_compare(
    claim: str,
    *,
    search_fn: SearchFn | None,
    fetch_fn: FetchFn,
    max_results: int,
) -> tuple[dict, list[str]]:
    variants = query_builder.build_geo_language_queries(claim)
    if not variants:
        return {}, []

    comparisons = {}
    risk_flags = []
    for bucket, queries in variants.items():
        provider_trace: list[str] = []
        try:
            if search_fn:
                raw_results = search_fn(queries, max_results, claim, provider_trace)
            else:
                from app.services.online_verifier import search_web_multi

                raw_results = search_web_multi(
                    queries,
                    max_results=max_results,
                    claim=claim,
                    provider_trace=provider_trace,
                )
        except Exception as exc:
            comparisons[bucket] = {
                "queries": queries,
                "search_providers": provider_trace,
                "error": str(exc),
                "raw_result_count": 0,
                "domains": [],
                "dominant_stance": "none",
            }
            continue

        sources = []
        evidence = []
        seen_urls = set()
        for result in raw_results[:max_results]:
            url = result.get("url") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            snapshot = fetch_fn(url, result)
            source = source_intel.classify_source(result, snapshot)
            sources.append(source)
            if snapshot.get("fetch_status") in {"ok", "pdf_ok"} and source.get("trust_tier") not in {"blocked"}:
                evidence.extend(evidence_service.extract_evidence_for_claim(claim, source, snapshot.get("text") or ""))
        sources = source_intel.annotate_cross_source_risks(sources)
        comparisons[bucket] = {
            "queries": queries,
            "search_providers": provider_trace,
            "raw_result_count": len(raw_results),
            "domains": [source.get("domain") for source in sources],
            "authoritative_count": source_intel.independent_source_count(sources, {"A", "B"}),
            "dominant_stance": _dominant_stance(evidence, sources),
            "risk_flags": sorted({flag for source in sources for flag in (source.get("risk_flags") or [])}),
        }

    stances = {
        item.get("dominant_stance")
        for item in comparisons.values()
        if item.get("dominant_stance") in {"support", "refute"}
    }
    if {"support", "refute"}.issubset(stances):
        risk_flags.append("geo_disagreement")
    return comparisons, risk_flags


def verify_claim(
    claim: str,
    *,
    index: int = 0,
    queries: list[str] | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    context: str = "",
    stage_callback: StageCallback | None = None,
    cache: VerificationCache | None = None,
    enable_geo_compare: bool = False,
) -> dict:
    claim_id = claim_id_for(claim, index)
    facts = claim_pipeline.extract_claim_facts(claim)
    built_queries = queries or query_builder.build_search_queries(claim)
    _emit_stage(
        stage_callback,
        {
            "claim_id": claim_id,
            "stage": "claim_started",
            "atomic_claim": claim,
            "claim_facts": to_plain_dict(facts),
            "queries": built_queries,
            "context_chars": len(context or ""),
        },
    )
    provider_trace: list[str] = []
    raw_results: list[dict] = []
    search_error = ""
    search_cache_key = cache_key_for("serp", {"claim": claim, "queries": built_queries, "max_results": max_results})
    search_cache_hit = False
    cached_search = cache.read("serp", search_cache_key) if cache else None
    if cached_search:
        raw_results = list(cached_search.get("raw_results") or [])
        provider_trace = list(cached_search.get("search_providers") or [])
        search_cache_hit = True
    elif search_fn:
        try:
            raw_results = search_fn(built_queries, max_results, claim, provider_trace)
        except Exception as exc:
            search_error = str(exc)
    else:
        from app.services.online_verifier import search_web_multi

        try:
            raw_results = search_web_multi(
                built_queries,
                max_results=max_results,
                claim=claim,
                provider_trace=provider_trace,
            )
        except Exception as exc:
            search_error = str(exc)

    if cache and not search_cache_hit and not search_error:
        cache.write(
            "serp",
            search_cache_key,
            {
                "claim": claim,
                "queries": built_queries,
                "max_results": max_results,
                "search_providers": provider_trace,
                "raw_results": raw_results[:max_results],
            },
        )

    _emit_stage(
        stage_callback,
        {
            "claim_id": claim_id,
            "stage": "search_completed",
            "queries": built_queries,
            "search_providers": provider_trace,
            "raw_result_count": len(raw_results),
            "search_error": search_error,
            "raw_results": raw_results[:max_results],
            "cache_hit": search_cache_hit,
            "cache_key": search_cache_key,
        },
    )

    fetch_fn = fetch_fn or fetching.fetch_source_snapshot
    sources: list[dict] = []
    all_evidence: list[dict] = []
    seen_urls = set()
    cache_audit = {
        "serp": {"key": search_cache_key, "hit": search_cache_hit},
        "snapshots": [],
        "evidence": [],
    }
    source_audit = []
    for result in raw_results[:max_results]:
        url = result.get("url") or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        snapshot_cache_key = cache_key_for("snapshot", {"url": url})
        snapshot_cache_hit = False
        cached_snapshot = cache.read("snapshot", snapshot_cache_key) if cache else None
        if cached_snapshot:
            snapshot = dict(cached_snapshot.get("snapshot") or {})
            snapshot_cache_hit = True
        else:
            snapshot = fetch_fn(url, result)
        if cache and not snapshot_cache_hit and snapshot.get("fetch_status") in {"ok", "pdf_ok"}:
            cache.write("snapshot", snapshot_cache_key, {"url": url, "snapshot": snapshot})

        source = source_intel.classify_source(result, snapshot)
        sources.append(source)
        extracted_count = 0
        evidence_cache_key = ""
        evidence_cache_hit = False
        if snapshot.get("fetch_status") in {"ok", "pdf_ok"} and source.get("trust_tier") not in {"blocked"}:
            content_hash = source.get("content_hash") or cache_key_for("body", snapshot.get("text") or "")
            evidence_cache_key = cache_key_for(
                "evidence",
                {
                    "claim": claim,
                    "source_url": source.get("url") or url,
                    "content_hash": content_hash,
                },
            )
            cached_evidence = cache.read("evidence", evidence_cache_key) if cache else None
            if cached_evidence:
                extracted = list(cached_evidence.get("evidence") or [])
                evidence_cache_hit = True
            else:
                extracted = evidence_service.extract_evidence_for_claim(claim, source, snapshot.get("text") or "")
                if cache:
                    cache.write("evidence", evidence_cache_key, {"evidence": extracted})
            extracted_count = len(extracted)
            all_evidence.extend(extracted)
        cache_audit["snapshots"].append({
            "url": url,
            "key": snapshot_cache_key,
            "hit": snapshot_cache_hit,
            "fetch_status": snapshot.get("fetch_status") or source.get("fetch_status"),
        })
        if evidence_cache_key:
            cache_audit["evidence"].append({
                "url": url,
                "key": evidence_cache_key,
                "hit": evidence_cache_hit,
                "evidence_count": extracted_count,
            })
        source_audit.append({
            "source_id": source.get("source_id") or "",
            "url": source.get("url") or url,
            "canonical_url": source.get("canonical_url") or "",
            "fetch_status": source.get("fetch_status") or snapshot.get("fetch_status") or "",
            "content_hash": source.get("content_hash") or "",
            "independence_group": source.get("independence_group") or "",
            "redirect_chain": source.get("redirect_chain") or [],
            "snapshot_cache_hit": snapshot_cache_hit,
            "evidence_cache_hit": evidence_cache_hit,
            "evidence_count": extracted_count,
        })
        _emit_stage(
            stage_callback,
            {
                "claim_id": claim_id,
                "stage": "source_fetched",
                "url": url,
                "source": source,
                "fetch_status": snapshot.get("fetch_status") or source.get("fetch_status"),
                "content_hash": source.get("content_hash") or snapshot.get("content_hash") or "",
                "evidence_added": extracted_count,
                "cache_hit": snapshot_cache_hit,
                "cache_key": snapshot_cache_key,
                "evidence_cache_hit": evidence_cache_hit,
                "evidence_cache_key": evidence_cache_key,
            },
        )

    sources = source_intel.annotate_cross_source_risks(sources)

    verdict, reason, confidence, risk_flags, counts = adjudication.adjudicate_claim(
        claim,
        sources,
        all_evidence,
        len(raw_results),
        search_error=search_error,
    )
    audit = {
        "version": 2,
        "method": "atomic_claim_multi_source_body_evidence",
        "search_summary_policy": "recall_only_never_supported",
        "queries": built_queries,
        "search_providers": provider_trace,
        "raw_result_count": len(raw_results),
        "fetched_source_count": sum(1 for source in sources if source.get("fetch_status") in {"ok", "pdf_ok"}),
        "independent_authoritative_sources": source_intel.independent_source_count(sources, {"A", "B"}),
        "evidence_counts": counts,
        "context_chars": len(context or ""),
        "cache": cache_audit,
        "source_audit": source_audit,
    }
    if search_error:
        audit["search_error"] = search_error
    if enable_geo_compare:
        geo_comparison, geo_risk_flags = _geo_compare(
            claim,
            search_fn=search_fn,
            fetch_fn=fetch_fn,
            max_results=max_results,
        )
        audit["geo_comparison"] = geo_comparison
        if geo_risk_flags:
            audit["pre_geo_verdict"] = {
                "verdict": verdict,
                "reason": reason,
                "confidence": confidence,
            }
            risk_flags = sorted(set(risk_flags + geo_risk_flags))
            verdict = "mixed"
            reason = (
                "不同语言或地区检索分支出现高可信正文支持/反驳冲突，"
                "需按地域、口径、时间范围或定义差异复核。"
            )
            confidence = min(confidence, 64)

    result = ClaimVerificationResult(
        claim_id=claim_id,
        atomic_claim=claim,
        claim_facts=facts,
        verdict=verdict,
        reason=reason,
        confidence=confidence,
        sources=sources,
        evidence=all_evidence,
        risk_flags=risk_flags,
        audit=audit,
    )
    payload = to_plain_dict(result)
    _emit_stage(
        stage_callback,
        {
            "claim_id": claim_id,
            "stage": "claim_completed",
            "result": payload,
        },
    )
    return payload


def verify_claims(
    claims: list[dict],
    *,
    max_claims: int = 50,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    context: str = "",
    stage_callback: StageCallback | None = None,
    cache: VerificationCache | None = None,
    enable_geo_compare: bool = False,
) -> list[dict]:
    selected = claim_pipeline.sort_claims_by_verification_risk(claims, max_claims)
    results = []
    for index, item in enumerate(selected):
        text = item.get("claim") or item.get("text") or ""
        if not text:
            continue
        results.append(
            verify_claim(
                text,
                index=index,
                search_fn=search_fn,
                fetch_fn=fetch_fn,
                context=context,
                stage_callback=stage_callback,
                cache=cache,
                enable_geo_compare=enable_geo_compare,
            )
        )
    return results
