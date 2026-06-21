from __future__ import annotations

import httpx

from app.services.verification.constants import (
    DEFAULT_MAX_RESULTS,
    SEARCH_PROVIDER,
)
from app.services.verification import ai_judge
from app.services.verification import adjudication
from app.services.verification import numeric_evidence
from app.services.verification import pipeline as verification_pipeline
from app.services.verification import query_builder
from app.services.verification import relevance
from app.services.verification import search_orchestrator
from app.services.verification import search_providers as search_provider_service
from app.services.verification import verdict as verdict_service
from app.services.verification.text_utils import (
    is_low_value_result as _text_is_low_value_result,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_duckduckgo_results(html: str, max_results: int) -> list[dict]:
    return search_provider_service.parse_duckduckgo_results(html, max_results)


def _parse_bing_results(html: str, max_results: int) -> list[dict]:
    return search_provider_service.parse_bing_results(html, max_results)


def _parse_baidu_results(html: str, max_results: int) -> list[dict]:
    return search_provider_service.parse_baidu_results(html, max_results)


def _parse_bing_academic_results(html: str, max_results: int) -> list[dict]:
    return search_provider_service.parse_bing_academic_results(html, max_results)


def _parse_brave_results(payload: dict, max_results: int) -> list[dict]:
    return search_provider_service.parse_brave_results(payload, max_results)


def _provider_results(provider: str, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    if provider in {"bing_academic", "bing_scholar", "academic_bing"}:
        return search_bing_academic(query, max_results=max_results)
    if provider in {"brave", "brave_api", "brave_search"}:
        return search_brave(query, max_results=max_results)
    if provider in {"bing", "bing_cn", "cn_bing"}:
        return search_bing_cn(query, max_results=max_results)
    if provider == "baidu":
        return search_baidu(query, max_results=max_results)
    if provider == "duckduckgo":
        return search_duckduckgo(query, max_results=max_results)
    raise ValueError(f"未知联网核验搜索源 {provider!r}")


def _provider_chain() -> list[str]:
    return search_provider_service.provider_chain()


def _search_web_with_provider(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> tuple[list[dict], str]:
    errors = []
    for provider in _provider_chain():
        try:
            results = _provider_results(provider, query, max_results=max_results)
        except Exception as exc:
            errors.append((provider, exc))
            logger.warning(f"联网核验搜索源 {provider!r} 失败 query={query}: {exc}")
            continue
        if results:
            logger.info(f"联网核验搜索源 {provider!r} 返回 {len(results)} 条 query={query}")
            if provider != SEARCH_PROVIDER:
                logger.info(f"联网核验使用兜底搜索源 {provider!r} query={query}")
            return results, provider

    if errors:
        raise errors[0][1]
    logger.warning(f"未知联网核验搜索源 {SEARCH_PROVIDER!r}，使用 cn.bing.com")
    return search_bing_cn(query, max_results=max_results), "bing_cn"


def search_web(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    results, _provider = _search_web_with_provider(query, max_results=max_results)
    return results


def _domestic_supplement_providers() -> list[str]:
    return search_provider_service.domestic_supplement_providers()


def _quality_supplement_providers(used_providers: set[str] | None = None) -> list[str]:
    return search_provider_service.quality_supplement_providers(used_providers)


def _result_key(item: dict) -> str:
    return search_orchestrator.result_key(item)


def _split_relevant_results(items: list[dict], claim: str, seen_urls: set[str]) -> tuple[list[dict], list[dict]]:
    return search_orchestrator.split_relevant_results(
        items,
        claim,
        seen_urls,
        relevance_fn=_result_relevance,
    )


def _needs_quality_supplement(results: list[dict], claim: str) -> bool:
    return search_orchestrator.needs_quality_supplement(results, claim)


def _record_provider(provider_trace: list[str] | None, provider: str) -> None:
    search_orchestrator.record_provider(provider_trace, provider)


def search_web_multi(
    queries: list[str],
    max_results: int = DEFAULT_MAX_RESULTS,
    claim: str = "",
    provider_trace: list[str] | None = None,
) -> list[dict]:
    return search_orchestrator.search_web_multi(
        queries,
        max_results=max_results,
        claim=claim,
        provider_trace=provider_trace,
        search_with_provider_fn=lambda query, limit: _search_web_with_provider(query, max_results=limit),
        provider_results_fn=lambda provider, query, limit: _provider_results(provider, query, max_results=limit),
        relevance_fn=_result_relevance,
    )


def search_duckduckgo(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    return search_provider_service.search_duckduckgo(query, max_results=max_results)


def search_bing_cn(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    return search_provider_service.search_bing_cn(query, max_results=max_results)


def search_bing_academic(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    return search_provider_service.search_bing_academic(query, max_results=max_results)


def search_baidu(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    return search_provider_service.search_baidu(query, max_results=max_results)


def search_brave(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    return search_provider_service.search_brave(query, max_results=max_results)


def _is_network_unavailable_error(exc: Exception) -> bool:
    return search_provider_service.is_network_unavailable_error(exc)


def _online_error_message(exc: Exception) -> str:
    return search_provider_service.online_error_message(exc)


def search_wikipedia(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    return search_provider_service.search_wikipedia(query, max_results=max_results)


def _clean_claim_text(claim: str) -> str:
    return query_builder.clean_claim_text(claim)


def _normalize_number(value: str) -> float | None:
    return numeric_evidence.normalize_number(value)


def _numeric_op_pattern() -> str:
    return numeric_evidence.numeric_op_pattern()


def _extract_numeric_mentions(text: str, include_operator: bool = True) -> list[dict]:
    return numeric_evidence.extract_numeric_mentions(text, include_operator=include_operator)


def _extract_numeric_constraints(claim: str) -> list[dict]:
    return numeric_evidence.extract_numeric_constraints(claim)


def _is_scientific_claim(text: str) -> bool:
    return numeric_evidence.is_scientific_claim(text)


def _has_protein_context(text: str) -> bool:
    return numeric_evidence.has_protein_context(text)


def _has_egg_context(text: str) -> bool:
    return numeric_evidence.has_egg_context(text)


def _numeric_context_related(claim_mention: dict, source_mention: dict) -> bool:
    return numeric_evidence.numeric_context_related(claim_mention, source_mention)


def _numeric_supports(claim_mention: dict, source_mention: dict) -> bool:
    return numeric_evidence.numeric_supports(claim_mention, source_mention)


def _numeric_conflicts(claim_mention: dict, source_mention: dict) -> bool:
    return numeric_evidence.numeric_conflicts(claim_mention, source_mention)


def _score_numeric_evidence(claim: str, results: list[dict]) -> dict:
    return numeric_evidence.score_numeric_evidence(claim, results)


def _scientific_search_queries(text: str) -> list[str]:
    return query_builder.scientific_search_queries(text)


def _domain_terms_for_claim(text: str) -> list[str]:
    return query_builder.domain_terms_for_claim(text)


def _build_search_query(claim: str) -> str:
    return query_builder.build_search_query(claim)


def _build_search_queries(claim: str) -> list[str]:
    return query_builder.build_search_queries(claim)


def _is_low_value_result(result: dict, claim: str) -> bool:
    return _text_is_low_value_result(result, claim)


def _result_relevance(claim: str, result: dict) -> dict:
    return relevance.result_relevance(claim, result)


def _filter_relevant_results(claim: str, results: list[dict]) -> list[dict]:
    return relevance.filter_relevant_results(claim, results)


def _score_results(claim: str, results: list[dict]) -> dict:
    return relevance.score_results(claim, results)


def _online_verdict(claim: dict, results: list[dict], metrics: dict) -> tuple[str, str, int]:
    return verdict_service.online_verdict(claim, results, metrics)


def _json_from_ai_text(text: str) -> dict:
    return ai_judge.json_from_ai_text(text)


def _default_model_config() -> tuple[str | None, str | None]:
    return ai_judge.default_model_config()


def _get_ai_verifier(model_name: str | None, provider_id: str | None):
    return ai_judge.get_ai_verifier(model_name, provider_id)


def _trim_context(context: str, limit: int = 6000) -> str:
    return ai_judge.trim_context(context, limit=limit)


def _ai_build_context_profile(gpt, context: str) -> dict:
    return ai_judge.build_context_profile(gpt, context)


def _ai_build_queries(gpt, claim: str, context_profile: dict | None = None, context: str = "") -> list[str]:
    return ai_judge.build_queries(gpt, claim, context_profile=context_profile, context=context)


def _ai_build_query(gpt, claim: str, context_profile: dict | None = None, context: str = "") -> str:
    return ai_judge.build_query(gpt, claim, context_profile=context_profile, context=context)


def _ai_judge_claim(gpt, claim: str, results: list[dict], context_profile: dict | None = None, context: str = "") -> dict:
    return ai_judge.judge_claim(gpt, claim, results, context_profile=context_profile, context=context)


def _ai_verdict_to_display(claim: dict, ai_result: dict) -> tuple[str, str, int]:
    return ai_judge.verdict_to_display(claim, ai_result)


def _enforce_numeric_verdict(
    claim: dict,
    verdict: str,
    reason: str,
    confidence: int,
    metrics: dict,
) -> tuple[str, str, int]:
    return verdict_service.enforce_numeric_verdict(claim, verdict, reason, confidence, metrics)


def verify_claims_online(
    verification: dict,
    max_claims: int = 50,
    model_name: str | None = None,
    provider_id: str | None = None,
    context: str = "",
    stage_callback: verification_pipeline.StageCallback | None = None,
    reuse_claim_results: dict[str, dict] | None = None,
    cache: verification_pipeline.VerificationCache | None = None,
    enable_geo_compare: bool = False,
) -> dict:
    """Enrich offline claim verification with deep body-evidence verification."""
    claims = list(verification.get("claims") or [])
    if not claims:
        verification["external_check"] = True
        verification["online_error"] = ""
        return verification

    selected = verification_pipeline.claim_pipeline.sort_claims_by_verification_risk(
        claims,
        max(1, min(int(max_claims or 50), 50)),
    )
    by_claim = {item.get("claim"): item for item in claims}
    checked = 0
    errors = []
    ai_verifier = None
    if model_name and provider_id:
        try:
            ai_verifier = _get_ai_verifier(model_name, provider_id)
        except Exception as exc:
            logger.warning(f"AI 核验模型初始化失败，将使用规则证据矩阵核验: {exc}")
    context_profile = {}
    if ai_verifier:
        try:
            context_profile = _ai_build_context_profile(ai_verifier, context)
        except Exception as exc:
            logger.warning(f"AI 上下文画像失败，将使用规则检索 query: {exc}")
            ai_verifier = None
    if not ai_verifier:
        logger.info("联网核验未启用 AI 结构化辅助：最终结论仍由规则证据矩阵决定")

    aggregate_sources = []
    aggregate_evidence = []
    aggregate_risk_flags = set()
    for index, claim in enumerate(selected):
        claim_text = claim.get("claim") or ""
        if not claim_text:
            continue
        try:
            reused_from_artifact = False
            pipeline_result = (reuse_claim_results or {}).get(claim_text)
            if pipeline_result:
                reused_from_artifact = True
                queries = pipeline_result.get("audit", {}).get("queries") or _build_search_queries(claim_text)
            else:
                try:
                    queries = (
                        _ai_build_queries(ai_verifier, claim_text, context_profile=context_profile, context=context)
                        if ai_verifier
                        else _build_search_queries(claim_text)
                    )
                except Exception as exc:
                    logger.warning(f"AI query 构建失败，将使用规则 query: {exc}")
                    queries = _build_search_queries(claim_text)
                query = queries[0] if queries else _build_search_query(claim_text)
                pipeline_result = verification_pipeline.verify_claim(
                    claim_text,
                    index=index,
                    queries=queries or [query],
                    search_fn=lambda built_queries, limit, pipeline_claim, trace: search_web_multi(
                        built_queries,
                        max_results=limit,
                        claim=pipeline_claim,
                        provider_trace=trace,
                    ),
                    max_results=DEFAULT_MAX_RESULTS,
                    context=context,
                    stage_callback=stage_callback,
                    cache=cache,
                    enable_geo_compare=enable_geo_compare,
                )
            query = queries[0] if queries else _build_search_query(claim_text)
            target = by_claim.get(claim_text)
            if not target:
                continue
            status = pipeline_result["verdict"]
            display_verdict = adjudication.legacy_display(status)
            audit = dict(pipeline_result.get("audit", {}))
            if reused_from_artifact:
                audit["reused_from_claim_artifact"] = True
            metrics = {
                "coverage": 0,
                "trusted_count": sum(
                    1 for source in pipeline_result.get("sources", []) if source.get("trust_tier") in {"A", "B"}
                ),
                "top_overlap": 0,
                **(audit.get("evidence_counts") or {}),
                "independent_authoritative_sources": audit.get(
                    "independent_authoritative_sources",
                    0,
                ),
            }
            target["online"] = {
                "checked": True,
                "query": query,
                "queries": queries or [query],
                "status": status,
                "verdict": display_verdict,
                "reason": pipeline_result["reason"],
                "confidence": pipeline_result["confidence"],
                "metrics": metrics,
                "sources": pipeline_result.get("sources", []),
                "evidence": pipeline_result.get("evidence", []),
                "risk_flags": pipeline_result.get("risk_flags", []),
                "audit": audit,
                "search_providers": audit.get("search_providers", []),
                "ai_checked": bool(ai_verifier) and not reused_from_artifact,
                "raw_result_count": audit.get("raw_result_count", 0),
                "filtered_result_count": len(pipeline_result.get("sources", [])),
                "claim_id": pipeline_result.get("claim_id"),
                "atomic_claim": pipeline_result.get("atomic_claim"),
                "claim_facts": pipeline_result.get("claim_facts"),
            }
            aggregate_sources.extend(pipeline_result.get("sources", []))
            aggregate_evidence.extend(pipeline_result.get("evidence", []))
            aggregate_risk_flags.update(pipeline_result.get("risk_flags", []))
            logger.info(
                "联网核验完成 claim=%s ai=%s raw=%s sources=%s verdict=%s",
                claim_text[:80],
                bool(ai_verifier) and not reused_from_artifact,
                audit.get("raw_result_count", 0),
                len(pipeline_result.get("sources", [])),
                status,
            )
            target["verdict"] = display_verdict
            target["reason"] = pipeline_result["reason"]
            target["confidence"] = pipeline_result["confidence"]
            target["machine_verdict"] = status
            checked += 1
        except Exception as exc:
            logger.warning(f"联网核验失败: {claim_text[:60]} {exc}")
            error_message = _online_error_message(exc)
            if error_message not in errors:
                errors.append(error_message)
            if _is_network_unavailable_error(exc):
                break

    summary = verdict_service.summarize_claims(verification, checked)

    verification["external_check"] = checked > 0
    verification["online_error"] = "; ".join(errors[:3])
    verification["claim_counts"] = {
        **(verification.get("claim_counts") or {}),
        "online_checked": checked,
        "online_supported": summary["supported_count"],
        "online_refuted": summary["refuted_count"],
        "online_mixed": summary["mixed_count"],
    }
    verification["sources"] = aggregate_sources
    verification["evidence"] = aggregate_evidence
    verification["risk_flags"] = sorted(aggregate_risk_flags)
    verification["overall"] = {
        **(verification.get("overall") or {}),
        "status": summary["status"],
        "score": summary["score"],
        "summary": summary["summary"],
        "note": "联网核验基于网页/PDF正文、来源分级、独立性和交叉证据；搜索摘要只作为召回线索，不能单独支持主张。",
    }
    verification["result"] = {
        "input": {"context_chars": len(context or "")},
        "overall": verification["overall"],
        "claim_counts": verification["claim_counts"],
        "claims": claims,
        "sources": aggregate_sources,
        "evidence": aggregate_evidence,
        "risk_flags": sorted(aggregate_risk_flags),
        "audit": {
            "version": 2,
            "depth": "deep",
            "source_policy": "authoritative",
            "search_summary_policy": "recall_only_never_supported",
        },
    }
    verification["claims"] = claims
    return verification
