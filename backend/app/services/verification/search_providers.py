from __future__ import annotations

import os
import socket
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from app.services.verification.constants import (
    BRAVE_SEARCH_ENDPOINT,
    BRAVE_UNAVAILABLE_MESSAGE,
    DEFAULT_MAX_RESULTS,
    NETWORK_UNAVAILABLE_MESSAGE,
    SEARCH_FALLBACK_PROVIDERS,
    SEARCH_PROVIDER,
    SEARCH_TIMEOUT,
)
from app.services.verification.text_utils import (
    clean_result_url,
    domain,
    is_low_value_result,
    result_item,
    strip_html,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def parse_duckduckgo_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result in soup.select(".result"):
        link = result.select_one(".result__a")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url:
            continue
        results.append(result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def parse_bing_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result in soup.select("li.b_algo"):
        link = result.select_one("h2 a")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".b_caption p")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url or not url.startswith(("http://", "https://")):
            continue
        results.append(result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def parse_baidu_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result in soup.select(".result, .c-container"):
        link = result.select_one("h3 a, .t a")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".c-abstract, .content-right_8Zs40, .c-span-last")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url:
            continue
        results.append(result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def parse_bing_academic_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    selectors = [
        "li.b_algo",
        ".aca_algo",
        ".academic_paper",
        ".b_entityTP",
        ".b_ans",
    ]
    for result in soup.select(", ".join(selectors)):
        link = result.select_one("h2 a, h3 a, a[href]")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".b_caption p, .aca_snippet, .snippet, p")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url or not url.startswith(("http://", "https://")):
            continue
        results.append(result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def parse_brave_results(payload: dict, max_results: int) -> list[dict]:
    results = []
    seen_urls = set()
    containers = [
        payload.get("web") or {},
        payload.get("news") or {},
    ]
    for container in containers:
        for raw in container.get("results") or []:
            title = strip_html(raw.get("title") or raw.get("name") or "")
            url = clean_result_url(str(raw.get("url") or ""))
            if not title or not url or not url.startswith(("http://", "https://")):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            snippet_parts = [strip_html(raw.get("description") or raw.get("snippet") or "")]
            for extra in raw.get("extra_snippets") or []:
                cleaned = strip_html(extra)
                if cleaned and cleaned not in snippet_parts:
                    snippet_parts.append(cleaned)
            results.append(result_item(title, url, " ".join(part for part in snippet_parts if part)))
            if len(results) >= max_results:
                return results
    return results


def provider_results(provider: str, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
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


def provider_chain() -> list[str]:
    providers = [SEARCH_PROVIDER, *SEARCH_FALLBACK_PROVIDERS]
    deduped = []
    for provider in providers:
        if provider and provider not in deduped:
            deduped.append(provider)
    return deduped or ["bing_cn"]


def search_web_with_provider(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> tuple[list[dict], str]:
    errors = []
    for provider in provider_chain():
        try:
            results = provider_results(provider, query, max_results=max_results)
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
    results, _provider = search_web_with_provider(query, max_results=max_results)
    return results


def domestic_supplement_providers() -> list[str]:
    providers = []
    for provider in ("bing_academic", "bing_cn", "baidu"):
        if provider not in provider_chain() and provider not in providers:
            providers.append(provider)
    return providers


def quality_supplement_providers(used_providers: set[str] | None = None) -> list[str]:
    used_providers = used_providers or set()
    providers = []
    for provider in ("brave", "bing_academic", "bing_cn", "baidu"):
        if provider not in used_providers and provider not in providers:
            providers.append(provider)
    return providers


def search_duckduckgo(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        )
    }
    with httpx.Client(timeout=SEARCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    if "complete the following challenge" in response.text.lower():
        logger.warning("DuckDuckGo returned a challenge page; falling back to Wikipedia search")
        return search_wikipedia(query, max_results=max_results)
    results = parse_duckduckgo_results(response.text, max_results=max_results)
    return results or search_wikipedia(query, max_results=max_results)


def search_bing_cn(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    url = f"https://cn.bing.com/search?q={quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    with httpx.Client(timeout=SEARCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    results = parse_bing_results(response.text, max_results=max_results)
    if not results or all(is_low_value_result(result, query) for result in results):
        try:
            baidu_results = search_baidu(query, max_results=max_results)
            return baidu_results or results
        except Exception as exc:
            logger.warning(f"Baidu fallback failed for query={query}: {exc}")
    return results


def search_bing_academic(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    url = f"https://cn.bing.com/academic/search?q={quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    with httpx.Client(timeout=SEARCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    results = parse_bing_academic_results(response.text, max_results=max_results)
    return results or parse_bing_results(response.text, max_results=max_results)


def search_baidu(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    url = f"https://www.baidu.com/s?wd={quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    with httpx.Client(timeout=SEARCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
    results = parse_baidu_results(response.text, max_results=max_results)
    return results or search_wikipedia(query, max_results=max_results)


def search_brave(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY 未配置，无法使用 Brave Search API")

    params = {
        "q": query,
        "count": max(1, min(max_results, 20)),
        "safesearch": os.getenv("BRAVE_SEARCH_SAFESEARCH", "moderate").strip() or "moderate",
        "spellcheck": 1,
    }
    country = os.getenv("BRAVE_SEARCH_COUNTRY", "CN").strip()
    search_lang = os.getenv("BRAVE_SEARCH_LANG", "zh-hans").strip()
    ui_lang = os.getenv("BRAVE_SEARCH_UI_LANG", "zh-CN").strip()
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang
    if ui_lang:
        params["ui_lang"] = ui_lang
    params["text_decorations"] = os.getenv("BRAVE_SEARCH_TEXT_DECORATIONS", "false").strip() or "false"

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "X-Subscription-Token": api_key,
    }
    with httpx.Client(timeout=SEARCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = client.get(BRAVE_SEARCH_ENDPOINT, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            if status_code in {401, 403}:
                raise RuntimeError("Brave Search API 鉴权失败，请检查 BRAVE_SEARCH_API_KEY") from exc
            if status_code == 429:
                raise RuntimeError("Brave Search API 请求过于频繁或额度不足") from exc
            raise

    results = parse_brave_results(response.json(), max_results=max_results)
    return results or search_wikipedia(query, max_results=max_results)


def search_wikipedia(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    terms = query.split()
    queries = [query]
    if len(terms) > 3:
        queries.append(" ".join(terms[:4]))
    if len(terms) > 1:
        queries.extend(terms[:4])

    seen = set()
    results = []
    headers = {
        "User-Agent": "ReelMind/0.1 knowledge verification (local user initiated)"
    }
    with httpx.Client(timeout=SEARCH_TIMEOUT, follow_redirects=True, headers=headers) as client:
        for item in queries:
            if not item or item in seen:
                continue
            seen.add(item)
            response = client.get(
                "https://zh.wikipedia.org/w/api.php",
                params={
                    "action": "opensearch",
                    "search": item,
                    "limit": max_results,
                    "namespace": 0,
                    "format": "json",
                },
            )
            response.raise_for_status()
            payload = response.json()
            titles = payload[1] if len(payload) > 1 else []
            snippets = payload[2] if len(payload) > 2 else []
            urls = payload[3] if len(payload) > 3 else []
            for title, snippet, url in zip(titles, snippets, urls):
                if url in {result["url"] for result in results}:
                    continue
                results.append({
                    "title": str(title)[:160],
                    "url": str(url),
                    "domain": domain(str(url)),
                    "snippet": str(snippet)[:260],
                    "trusted": True,
                })
                if len(results) >= max_results:
                    return results
    return results


def is_network_unavailable_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.NetworkError, httpx.TimeoutException, socket.gaierror)):
        return True

    message = str(exc).lower()
    return any(
        hint in message
        for hint in (
            "network is unreachable",
            "errno 101",
            "name or service not known",
            "temporary failure in name resolution",
            "nodename nor servname provided",
            "connection refused",
            "connect timeout",
            "timed out",
        )
    )


def online_error_message(exc: Exception) -> str:
    if is_network_unavailable_error(exc):
        if SEARCH_PROVIDER in {"brave", "brave_api", "brave_search"}:
            return BRAVE_UNAVAILABLE_MESSAGE
        return NETWORK_UNAVAILABLE_MESSAGE
    return f"联网检索失败：{exc}"
