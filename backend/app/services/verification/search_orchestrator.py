from __future__ import annotations

from collections.abc import Callable

from app.services.verification.constants import DEFAULT_MAX_RESULTS
from app.services.verification import relevance
from app.services.verification import search_providers
from app.utils.logger import get_logger

logger = get_logger(__name__)

ProviderResultsFn = Callable[[str, str, int], list[dict]]
SearchWithProviderFn = Callable[[str, int], tuple[list[dict], str]]
RelevanceFn = Callable[[str, dict], dict]


def result_key(item: dict) -> str:
    return item.get("url") or f"{item.get('title', '')}|{item.get('snippet', '')}"


def split_relevant_results(
    items: list[dict],
    claim: str,
    seen_urls: set[str],
    relevance_fn: RelevanceFn | None = None,
) -> tuple[list[dict], list[dict]]:
    relevance_fn = relevance_fn or relevance.result_relevance
    relevant = []
    fallback = []
    for item in items:
        key = result_key(item)
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        if claim and not relevance_fn(claim, item)["relevant"]:
            fallback.append(item)
            continue
        relevant.append(item)
    return relevant, fallback


def needs_quality_supplement(results: list[dict], claim: str) -> bool:
    if not claim:
        return False
    if not results:
        return True
    return len(results) < 2 or not any(result.get("trusted") for result in results)


def record_provider(provider_trace: list[str] | None, provider: str) -> None:
    if provider_trace is not None and provider and provider not in provider_trace:
        provider_trace.append(provider)


def search_web_multi(
    queries: list[str],
    max_results: int = DEFAULT_MAX_RESULTS,
    claim: str = "",
    provider_trace: list[str] | None = None,
    search_with_provider_fn: SearchWithProviderFn | None = None,
    provider_results_fn: ProviderResultsFn | None = None,
    relevance_fn: RelevanceFn | None = None,
) -> list[dict]:
    search_with_provider_fn = search_with_provider_fn or (
        lambda query, limit: search_providers.search_web_with_provider(query, max_results=limit)
    )
    provider_results_fn = provider_results_fn or (
        lambda provider, query, limit: search_providers.provider_results(provider, query, max_results=limit)
    )
    relevance_fn = relevance_fn or relevance.result_relevance

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
            query_results, provider = search_with_provider_fn(query, max_results)
            used_providers.add(provider)
            record_provider(provider_trace, provider)
        except Exception as exc:
            logger.warning(f"联网核验单条检索失败 query={query}: {exc}")
            failures.append(exc)
            continue

        query_relevant, query_fallback = split_relevant_results(
            query_results,
            claim,
            seen_urls,
            relevance_fn=relevance_fn,
        )

        if claim and not query_relevant:
            for provider in search_providers.domestic_supplement_providers():
                try:
                    supplement_results = provider_results_fn(provider, query, max_results)
                except Exception as exc:
                    logger.warning(f"联网核验国内补充检索失败 provider={provider!r} query={query}: {exc}")
                    continue
                used_providers.add(provider)
                record_provider(provider_trace, provider)
                logger.info(f"联网核验国内补充搜索源 {provider!r} 返回 {len(supplement_results)} 条 query={query}")
                relevant, fallback = split_relevant_results(
                    supplement_results,
                    claim,
                    seen_urls,
                    relevance_fn=relevance_fn,
                )
                query_relevant.extend(relevant)
                query_fallback.extend(fallback)
                if query_relevant:
                    break

        if claim and needs_quality_supplement(query_relevant, claim):
            for provider in search_providers.quality_supplement_providers(used_providers):
                try:
                    supplement_results = provider_results_fn(provider, query, max_results)
                except Exception as exc:
                    logger.warning(f"联网核验质量补充检索失败 provider={provider!r} query={query}: {exc}")
                    continue
                used_providers.add(provider)
                record_provider(provider_trace, provider)
                logger.info(f"联网核验质量补充搜索源 {provider!r} 返回 {len(supplement_results)} 条 query={query}")
                relevant, fallback = split_relevant_results(
                    supplement_results,
                    claim,
                    seen_urls,
                    relevance_fn=relevance_fn,
                )
                query_relevant.extend(relevant)
                query_fallback.extend(fallback)
                if not needs_quality_supplement(query_relevant, claim):
                    break

        fallback_results.extend(query_fallback)
        for item in query_relevant:
            results.append(item)
            if len(results) >= max_results:
                return results
    if failures and len(failures) == len(seen_queries) and not results and not fallback_results:
        raise failures[0]
    return (results + fallback_results)[:max_results]
