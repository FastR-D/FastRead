from __future__ import annotations

import re
import httpx

from app.services.verification.constants import (
    DEFAULT_MAX_RESULTS,
    SEARCH_PROVIDER,
)
from app.services.verification import ai_judge
from app.services.verification import numeric_evidence
from app.services.verification import query_builder
from app.services.verification import relevance
from app.services.verification import search_providers as search_provider_service
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
    return item.get("url") or f"{item.get('title', '')}|{item.get('snippet', '')}"


def _split_relevant_results(items: list[dict], claim: str, seen_urls: set[str]) -> tuple[list[dict], list[dict]]:
    relevant = []
    fallback = []
    for item in items:
        key = _result_key(item)
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        if claim and not _result_relevance(claim, item)["relevant"]:
            fallback.append(item)
            continue
        relevant.append(item)
    return relevant, fallback


def _needs_quality_supplement(results: list[dict], claim: str) -> bool:
    if not claim:
        return False
    if not results:
        return True
    return len(results) < 2 or not any(result.get("trusted") for result in results)


def _record_provider(provider_trace: list[str] | None, provider: str) -> None:
    if provider_trace is not None and provider and provider not in provider_trace:
        provider_trace.append(provider)


def search_web_multi(
    queries: list[str],
    max_results: int = DEFAULT_MAX_RESULTS,
    claim: str = "",
    provider_trace: list[str] | None = None,
) -> list[dict]:
    seen_queries = set()
    seen_urls = set()
    results = []
    fallback_results = []
    failures = []
    for query in queries:
        query = (query or "").strip()
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)
        logger.info(f"联网核验检索 query={query}")
        used_providers = set()
        try:
            query_results, provider = _search_web_with_provider(query, max_results=max_results)
            used_providers.add(provider)
            _record_provider(provider_trace, provider)
        except Exception as exc:
            logger.warning(f"联网核验单条检索失败 query={query}: {exc}")
            failures.append(exc)
            continue

        query_relevant, query_fallback = _split_relevant_results(query_results, claim, seen_urls)

        if claim and not query_relevant:
            for provider in _domestic_supplement_providers():
                try:
                    supplement_results = _provider_results(provider, query, max_results=max_results)
                except Exception as exc:
                    logger.warning(f"联网核验国内补充检索失败 provider={provider!r} query={query}: {exc}")
                    continue
                used_providers.add(provider)
                _record_provider(provider_trace, provider)
                logger.info(f"联网核验国内补充搜索源 {provider!r} 返回 {len(supplement_results)} 条 query={query}")
                relevant, fallback = _split_relevant_results(supplement_results, claim, seen_urls)
                query_relevant.extend(relevant)
                query_fallback.extend(fallback)
                if query_relevant:
                    break

        if claim and _needs_quality_supplement(query_relevant, claim):
            for provider in _quality_supplement_providers(used_providers):
                try:
                    supplement_results = _provider_results(provider, query, max_results=max_results)
                except Exception as exc:
                    logger.warning(f"联网核验质量补充检索失败 provider={provider!r} query={query}: {exc}")
                    continue
                used_providers.add(provider)
                _record_provider(provider_trace, provider)
                logger.info(f"联网核验质量补充搜索源 {provider!r} 返回 {len(supplement_results)} 条 query={query}")
                relevant, fallback = _split_relevant_results(supplement_results, claim, seen_urls)
                query_relevant.extend(relevant)
                query_fallback.extend(fallback)
                if not _needs_quality_supplement(query_relevant, claim):
                    break

        fallback_results.extend(query_fallback)
        for item in query_relevant:
            results.append(item)
            if len(results) >= max_results:
                return results
    if failures and len(failures) == len(seen_queries) and not results and not fallback_results:
        raise failures[0]
    return (results + fallback_results)[:max_results]


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
    if not results:
        return (
            "未找到外部证据",
            "联网检索没有返回可用结果，不能据此判断该主张是否属实。",
            min(int(claim.get("confidence", 50)), 45),
        )

    coverage = metrics["coverage"]
    trusted_count = metrics["trusted_count"]
    top_overlap = metrics["top_overlap"]
    if metrics.get("numeric_claim") and metrics.get("numeric_match_count", 0) <= 0:
        if metrics.get("numeric_conflict_count", 0) > 0:
            return (
                "相关资料未支持精确数字",
                "检索到相关资料，但可比数字与主张中的数值、范围或单位不一致；不能直接视为外部佐证。",
                min(max(int(claim.get("confidence", 50)), 45), 58),
            )
        return (
            "精确数字仍待核实",
            "检索结果与主题相关，但没有命中能支持该数字、范围或单位的明确证据。",
            min(max(int(claim.get("confidence", 50)), 45), 60),
        )

    if trusted_count > 0 and coverage >= 0.35:
        return (
            "找到权威相关资料",
            "检索结果中存在权威来源，且与主张有较高文本相关度；仍需用户打开来源确认细节。",
            max(int(claim.get("confidence", 50)), 78),
        )
    if coverage >= 0.4 or top_overlap >= 5:
        return (
            "找到相关资料",
            "检索结果与主张主题相关，但来源权威性或证据强度不足，不能直接视为已证实。",
            max(int(claim.get("confidence", 50)), 68),
        )
    return (
        "证据仍不足",
        "检索结果较少或相关度偏低，当前仍应保持核实状态。",
        min(max(int(claim.get("confidence", 50)), 50), 62),
    )


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
    if not metrics.get("numeric_claim") or metrics.get("numeric_match_count", 0) > 0:
        return verdict, reason, confidence
    if verdict not in {"找到权威相关资料", "找到相关资料", "AI 判断有外部佐证"}:
        return verdict, reason, confidence

    if metrics.get("numeric_conflict_count", 0) > 0:
        return (
            "相关资料未支持精确数字",
            "检索结果与主题相关，但可比数字与主张中的数值、范围或单位不一致；不能当作已证实。",
            min(max(int(claim.get("confidence", 50)), 45), 58),
        )
    return (
        "精确数字仍待核实",
        "检索结果与主题相关，但没有明确支持主张中数字、范围或单位的证据。",
        min(max(int(claim.get("confidence", 50)), 45), 60),
    )


def verify_claims_online(
    verification: dict,
    max_claims: int = 8,
    model_name: str | None = None,
    provider_id: str | None = None,
    context: str = "",
) -> dict:
    """Enrich offline claim verification with optional web search evidence."""
    claims = list(verification.get("claims") or [])
    if not claims:
        verification["external_check"] = True
        verification["online_error"] = ""
        return verification

    selected = sorted(claims, key=lambda item: item.get("priority", 0), reverse=True)[:max_claims]
    by_claim = {item.get("claim"): item for item in claims}
    checked = 0
    errors = []
    ai_verifier = None
    try:
        ai_verifier = _get_ai_verifier(model_name, provider_id)
    except Exception as exc:
        logger.warning(f"AI 核验模型初始化失败，将使用普通搜索核验: {exc}")
    context_profile = _ai_build_context_profile(ai_verifier, context) if ai_verifier else {}
    if not ai_verifier:
        logger.info("联网核验未启用 AI 判断：请求未提供模型，且未找到可用默认模型")

    for claim in selected:
        claim_text = claim.get("claim") or ""
        if not claim_text:
            continue
        try:
            queries = (
                _ai_build_queries(ai_verifier, claim_text, context_profile=context_profile, context=context)
                if ai_verifier
                else _build_search_queries(claim_text)
            )
            query = queries[0] if queries else _build_search_query(claim_text)
            search_providers = []
            raw_results = search_web_multi(
                queries or [query],
                max_results=DEFAULT_MAX_RESULTS,
                claim=claim_text,
                provider_trace=search_providers,
            )
            results = _filter_relevant_results(claim_text, raw_results)
            metrics = _score_results(claim_text, results)
            ai_result = None
            if ai_verifier and raw_results:
                ai_result = _ai_judge_claim(
                    ai_verifier,
                    claim_text,
                    raw_results,
                    context_profile=context_profile,
                    context=context,
                )
                results = ai_result["sources"]
                metrics = _score_results(claim_text, results)
                verdict, reason, confidence = _ai_verdict_to_display(claim, ai_result)
            else:
                verdict, reason, confidence = _online_verdict(claim, results, metrics)
            verdict, reason, confidence = _enforce_numeric_verdict(
                claim,
                verdict,
                reason,
                confidence,
                metrics,
            )
            target = by_claim.get(claim_text)
            if not target:
                continue
            target["online"] = {
                "checked": True,
                "query": query,
                "queries": queries or [query],
                "verdict": verdict,
                "reason": reason,
                "confidence": confidence,
                "metrics": metrics,
                "sources": results,
                "search_providers": search_providers,
                "ai_checked": bool(ai_result),
                "raw_result_count": len(raw_results),
                "filtered_result_count": len(results),
            }
            logger.info(
                "联网核验完成 claim=%s ai=%s raw=%s useful=%s verdict=%s",
                claim_text[:80],
                bool(ai_result),
                len(raw_results),
                len(results),
                verdict,
            )
            target["verdict"] = verdict
            target["reason"] = reason
            target["confidence"] = confidence
            checked += 1
        except Exception as exc:
            logger.warning(f"联网核验失败: {claim_text[:60]} {exc}")
            error_message = _online_error_message(exc)
            if error_message not in errors:
                errors.append(error_message)
            if _is_network_unavailable_error(exc):
                break

    checked_claims = [claim for claim in claims if claim.get("online", {}).get("checked")]
    supported_count = sum(
        1
        for claim in checked_claims
        if claim.get("online", {}).get("verdict") in {"找到权威相关资料", "找到相关资料", "AI 判断有外部佐证"}
    )
    refuted_count = sum(
        1
        for claim in checked_claims
        if claim.get("online", {}).get("verdict") == "AI 判断存在反证"
    )
    insufficient_count = sum(
        1
        for claim in claims
        if claim.get("verdict") in {
            "证据不足",
            "缺少来源",
            "需重点核实",
            "证据仍不足",
            "未找到外部证据",
            "精确数字仍待核实",
            "相关资料未支持精确数字",
        }
    )

    base_score = int(verification.get("overall", {}).get("score") or 50)
    next_score = base_score + supported_count * 7
    next_score = max(0, min(100, next_score))
    status = "联网核验完成" if checked else "保持离线核验"
    if checked and insufficient_count > supported_count:
        status = "仍需核实"
    if checked and supported_count >= max(1, checked // 2) and insufficient_count <= supported_count:
        status = "找到外部佐证"

    verification["external_check"] = checked > 0
    verification["online_error"] = "; ".join(errors[:3])
    verification["claim_counts"] = {
        **(verification.get("claim_counts") or {}),
        "online_checked": checked,
        "online_supported": supported_count,
        "online_refuted": refuted_count,
    }
    verification["overall"] = {
        **(verification.get("overall") or {}),
        "status": status,
        "score": next_score,
        "summary": (
            f"已联网核验 {checked} 条主张，找到 {supported_count} 条外部佐证、{refuted_count} 条反证。"
            if checked
            else "联网核验未完成，当前结果仍基于离线文本证据判断。"
        ),
        "note": "联网核验基于搜索结果标题、摘要和来源域名做证据扫描，不等同于人工事实核查。",
    }
    verification["claims"] = claims
    return verification
