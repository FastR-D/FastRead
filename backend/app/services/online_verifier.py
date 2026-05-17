from __future__ import annotations

import os
import re
import socket
import json
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from app.gpt.gpt_factory import GPTFactory
from app.models.model_config import ModelConfig
from app.db.model_dao import get_all_models
from app.services.provider import ProviderService
from app.utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

SEARCH_TIMEOUT = float(os.getenv("ONLINE_VERIFY_TIMEOUT", "8"))
DEFAULT_MAX_RESULTS = int(os.getenv("ONLINE_VERIFY_RESULTS", "5"))
SEARCH_PROVIDER = os.getenv("ONLINE_VERIFY_SEARCH_PROVIDER", "bing_academic").strip().lower()
SEARCH_FALLBACK_PROVIDERS = [
    provider.strip().lower()
    for provider in os.getenv(
        "ONLINE_VERIFY_SEARCH_FALLBACK_PROVIDERS",
        "baidu_xueshu,baidu,bing_cn,brave",
    ).split(",")
    if provider.strip()
]
BRAVE_SEARCH_ENDPOINT = os.getenv(
    "BRAVE_SEARCH_ENDPOINT",
    "https://api.search.brave.com/res/v1/web/search",
).strip()
NETWORK_UNAVAILABLE_MESSAGE = (
    "当前运行环境无法访问外网，已保留离线核验结果；请检查网络、代理或 Docker/WSL 网络配置后重试。"
)
BRAVE_UNAVAILABLE_MESSAGE = (
    "Brave Search API 在当前网络链路不可达，已尝试切换国内搜索兜底；"
    "如需强制使用 Brave，请让 Docker 容器走可访问 api.search.brave.com 的代理。"
)

TRUSTED_DOMAIN_HINTS = (
    ".gov",
    ".edu",
    "who.int",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "un.org",
    "stats.gov.cn",
    "gov.cn",
    "pku.edu.cn",
    "tsinghua.edu.cn",
    "cnki.net",
    "wanfangdata.com.cn",
    "cqvip.com",
    "xueshu.baidu.com",
    "nature.com",
    "science.org",
)

AUTHORITY_TITLE_HINTS = (
    "官方",
    "国家",
    "政府",
    "统计局",
    "世界银行",
    "国际货币基金",
    "研究",
    "报告",
    "论文",
    "学报",
    "期刊",
    "硕士",
    "博士",
)

KEEP_CHINESE_TERMS = {
    "边际成本",
    "边际效用",
    "价格歧视",
    "集体行动",
    "隐性成本",
    "激励机制",
    "李梅",
    "柯蒂斯李梅",
    "燃烧弹",
    "低空轰炸",
    "东京大轰炸",
}

GENERIC_SEARCH_TERMS = {
    "关键",
    "属性",
    "节点",
    "路径",
    "后代",
    "叶子",
    "数量",
    "相同",
    "包含",
    "必须",
    "所有",
    "任一",
    "解释",
    "定义",
    "意思",
    "词语",
}

LOW_VALUE_SOURCE_HINTS = (
    "baike.baidu.com",
    "hanyu.baidu.com",
    "cidian",
    "hydcd",
    "zdic.net",
    "cidian.qianp.com",
)


def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    words = set(re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    grams = {chinese[i:i + 2] for i in range(max(len(chinese) - 1, 0))}
    return {token for token in words | grams if len(token) >= 2}


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _clean_result_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return url


def _result_item(title: str, url: str, snippet: str = "") -> dict:
    return {
        "title": title[:160],
        "url": url,
        "domain": _domain(url),
        "snippet": snippet[:260],
        "trusted": _is_trusted_source(title, url),
    }


def _is_trusted_source(title: str, url: str) -> bool:
    domain = _domain(url)
    title_text = title or ""
    if any(hint in domain for hint in LOW_VALUE_SOURCE_HINTS):
        return False
    return any(hint in domain for hint in TRUSTED_DOMAIN_HINTS) or any(
        hint in title_text for hint in AUTHORITY_TITLE_HINTS
    )


def _parse_duckduckgo_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result in soup.select(".result"):
        link = result.select_one(".result__a")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = _clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url:
            continue
        results.append(_result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def _parse_bing_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result in soup.select("li.b_algo"):
        link = result.select_one("h2 a")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = _clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".b_caption p")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url or not url.startswith(("http://", "https://")):
            continue
        results.append(_result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def _parse_baidu_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result in soup.select(".result, .c-container"):
        link = result.select_one("h3 a, .t a")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = _clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".c-abstract, .content-right_8Zs40, .c-span-last")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url:
            continue
        results.append(_result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def _parse_baidu_xueshu_results(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for result in soup.select(".result, .sc_content, .c_font, .result-container"):
        link = result.select_one("h3 a, .t a, .sc_content h3 a, a[href]")
        if not link:
            continue
        title = link.get_text(" ", strip=True)
        url = _clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".c_abstract, .c-abstract, .abstract, .sc_content")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url:
            continue
        results.append(_result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def _parse_bing_academic_results(html: str, max_results: int) -> list[dict]:
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
        url = _clean_result_url(link.get("href") or "")
        snippet_el = result.select_one(".b_caption p, .aca_snippet, .snippet, p")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not url or not url.startswith(("http://", "https://")):
            continue
        results.append(_result_item(title, url, snippet))
        if len(results) >= max_results:
            break
    return results


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return BeautifulSoup(str(text), "html.parser").get_text(" ", strip=True)


def _parse_brave_results(payload: dict, max_results: int) -> list[dict]:
    results = []
    seen_urls = set()
    containers = [
        payload.get("web") or {},
        payload.get("news") or {},
    ]
    for container in containers:
        for raw in container.get("results") or []:
            title = _strip_html(raw.get("title") or raw.get("name") or "")
            url = _clean_result_url(str(raw.get("url") or ""))
            if not title or not url or not url.startswith(("http://", "https://")):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            snippet_parts = [_strip_html(raw.get("description") or raw.get("snippet") or "")]
            for extra in raw.get("extra_snippets") or []:
                cleaned = _strip_html(extra)
                if cleaned and cleaned not in snippet_parts:
                    snippet_parts.append(cleaned)
            results.append(_result_item(title, url, " ".join(part for part in snippet_parts if part)))
            if len(results) >= max_results:
                return results
    return results


def _provider_results(provider: str, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    if provider in {"baidu_xueshu", "xueshu_baidu", "baidu_scholar"}:
        return search_baidu_xueshu(query, max_results=max_results)
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
    providers = [SEARCH_PROVIDER, *SEARCH_FALLBACK_PROVIDERS]
    deduped = []
    for provider in providers:
        if provider and provider not in deduped:
            deduped.append(provider)
    return deduped or ["bing_cn"]


def search_web(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    errors = []
    for provider in _provider_chain():
        try:
            results = _provider_results(provider, query, max_results=max_results)
        except Exception as exc:
            errors.append((provider, exc))
            logger.warning(f"联网核验搜索源 {provider!r} 失败 query={query}: {exc}")
            continue
        if results:
            if provider != SEARCH_PROVIDER:
                logger.info(f"联网核验使用兜底搜索源 {provider!r} query={query}")
            return results

    if errors:
        raise errors[0][1]
    logger.warning(f"未知联网核验搜索源 {SEARCH_PROVIDER!r}，使用 cn.bing.com")
    return search_bing_cn(query, max_results=max_results)


def _domestic_supplement_providers() -> list[str]:
    providers = []
    for provider in ("baidu_xueshu", "bing_academic", "baidu", "bing_cn"):
        if provider not in _provider_chain() and provider not in providers:
            providers.append(provider)
    return providers


def search_web_multi(
    queries: list[str],
    max_results: int = DEFAULT_MAX_RESULTS,
    claim: str = "",
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
        try:
            query_results = search_web(query, max_results=max_results)
        except Exception as exc:
            logger.warning(f"联网核验单条检索失败 query={query}: {exc}")
            failures.append(exc)
            continue
        query_relevant = []
        query_fallback = []
        for item in query_results:
            url = item.get("url") or ""
            key = url or f"{item.get('title', '')}|{item.get('snippet', '')}"
            if not key or key in seen_urls:
                continue
            seen_urls.add(key)
            if claim and not _result_relevance(claim, item)["relevant"]:
                query_fallback.append(item)
                continue
            query_relevant.append(item)
        if claim and not query_relevant:
            try:
                for provider in _domestic_supplement_providers():
                    for item in _provider_results(provider, query, max_results=max_results):
                        url = item.get("url") or ""
                        key = url or f"{item.get('title', '')}|{item.get('snippet', '')}"
                        if not key or key in seen_urls:
                            continue
                        seen_urls.add(key)
                        if not _result_relevance(claim, item)["relevant"]:
                            query_fallback.append(item)
                            continue
                        query_relevant.append(item)
                    if query_relevant:
                        break
            except Exception as exc:
                logger.warning(f"联网核验国内补充检索失败 query={query}: {exc}")
        if claim and not query_relevant and SEARCH_PROVIDER in {"bing", "bing_cn", "cn_bing"}:
            try:
                for item in search_baidu(query, max_results=max_results):
                    url = item.get("url") or ""
                    key = url or f"{item.get('title', '')}|{item.get('snippet', '')}"
                    if not key or key in seen_urls:
                        continue
                    seen_urls.add(key)
                    if not _result_relevance(claim, item)["relevant"]:
                        query_fallback.append(item)
                        continue
                    query_relevant.append(item)
            except Exception as exc:
                logger.warning(f"联网核验百度补充检索失败 query={query}: {exc}")
        fallback_results.extend(query_fallback)
        for item in query_relevant:
            results.append(item)
            if len(results) >= max_results:
                return results
    if failures and len(failures) == len(seen_queries) and not results and not fallback_results:
        raise failures[0]
    return (results + fallback_results)[:max_results]


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
    results = _parse_duckduckgo_results(response.text, max_results=max_results)
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
    results = _parse_bing_results(response.text, max_results=max_results)
    if not results or all(_is_low_value_result(result, query) for result in results):
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
    results = _parse_bing_academic_results(response.text, max_results=max_results)
    return results or _parse_bing_results(response.text, max_results=max_results)


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
    results = _parse_baidu_results(response.text, max_results=max_results)
    return results or search_wikipedia(query, max_results=max_results)


def search_baidu_xueshu(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
    url = f"https://xueshu.baidu.com/s?wd={quote_plus(query)}"
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
    results = _parse_baidu_xueshu_results(response.text, max_results=max_results)
    return results or _parse_baidu_results(response.text, max_results=max_results)


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

    results = _parse_brave_results(response.json(), max_results=max_results)
    return results or search_wikipedia(query, max_results=max_results)


def _is_network_unavailable_error(exc: Exception) -> bool:
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


def _online_error_message(exc: Exception) -> str:
    if _is_network_unavailable_error(exc):
        if SEARCH_PROVIDER in {"brave", "brave_api", "brave_search"}:
            return BRAVE_UNAVAILABLE_MESSAGE
        return NETWORK_UNAVAILABLE_MESSAGE
    return f"联网检索失败：{exc}"


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
                    "domain": _domain(str(url)),
                    "snippet": str(snippet)[:260],
                    "trusted": True,
                })
                if len(results) >= max_results:
                    return results
    return results


def _clean_claim_text(claim: str) -> str:
    text = re.sub(r"^\s*(引申|应用|经济学解释|总结|核心观点|结论)[：:]\s*", "", claim or "")
    text = re.sub(r"[*_#>`\"'“”]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _domain_terms_for_claim(text: str) -> list[str]:
    terms = []
    if any(hint in text for hint in ("黑色节点", "红黑", "黑高", "黑路同", "叶子节点")):
        terms.extend(["红黑树", "黑高", "性质"])
    if any(hint.lower() in text.lower() for hint in ("b-tree", "b树", "二叉搜索树", "平衡树")):
        terms.extend(["数据结构", "树"])
    if any(hint.lower() in text.lower() for hint in ("李梅", "柯蒂斯", "lemay", "b-29", "m69", "燃烧弹", "东京大轰炸", "裸奔式轰炸")):
        terms.extend([
            "Curtis LeMay",
            "柯蒂斯 李梅",
            "B-29",
            "M69 incendiary bombs",
            "M69 燃烧弹",
            "Tokyo firebombing",
            "东京大轰炸",
        ])
    return terms


def _build_search_query(claim: str) -> str:
    text = _clean_claim_text(claim)
    if not text:
        return ""

    domain_terms = _domain_terms_for_claim(text)
    phrase = re.split(r"[。；;\n]", text, maxsplit=1)[0].strip()
    phrase = re.sub(r"^[^：:]{1,12}[：:]\s*", "", phrase)
    if 8 <= len(phrase) <= 90:
        return " ".join([*domain_terms, phrase]).strip()

    parts = re.split(r"[，,。；;：:（）()\[\]【】、\s]+|——|--", text)
    stop_words = {
        "因为",
        "所以",
        "但是",
        "如果",
        "没有",
        "任何",
        "所有",
        "这个",
        "一种",
        "进行",
        "通过",
        "反而",
        "就是",
        "不是",
        "可以",
        "需要",
        "例如",
        "以及",
        *GENERIC_SEARCH_TERMS,
    }
    terms = list(domain_terms)
    for part in parts:
        item = part.strip()
        if not item or item in stop_words:
            continue
        if re.fullmatch(r"[a-zA-Z]{1,3}", item):
            continue
        chinese_only = "".join(re.findall(r"[\u4e00-\u9fff]", item))
        if item in KEEP_CHINESE_TERMS or len(chinese_only) >= 3:
            term = item[:18]
        else:
            term = item
        if len(term) >= 2 and term not in terms and term not in stop_words:
            terms.append(term)
        if len(terms) >= 8:
            break
    return " ".join(terms) or (claim or "")[:60]


def _build_search_queries(claim: str) -> list[str]:
    text = _clean_claim_text(claim)
    primary = _build_search_query(text)
    queries = [primary] if primary else []
    lower = text.lower()

    if any(hint in lower for hint in ("李梅", "柯蒂斯", "lemay", "b-29", "m69", "燃烧弹", "东京大轰炸", "裸奔式轰炸")):
        queries = [
            "Curtis LeMay B-29 M69 Tokyo firebombing",
            "Curtis LeMay B-29 removed guns turrets M69 incendiary Tokyo raid",
            "Curtis LeMay low altitude incendiary bombing B-29 M69",
            "柯蒂斯 李梅 B-29 M69 燃烧弹 低空轰炸",
            "李梅 B-29 拆除 机枪 炮塔 M69 燃烧弹 低空轰炸",
            *queries,
        ]

    if any(hint in text for hint in ("黑色节点", "红黑", "黑高", "黑路同", "叶子节点")):
        queries.extend([
            "红黑树 黑高 性质 所有叶子 黑色节点 数量 相同",
            "red black tree property same number of black nodes paths leaves",
        ])

    deduped = []
    for query in queries:
        query = re.sub(r"\s+", " ", query or "").strip()
        if query and query not in deduped:
            deduped.append(query)
    return deduped[:4]


def _is_low_value_result(result: dict, claim: str) -> bool:
    domain = result.get("domain") or _domain(result.get("url") or "")
    title = result.get("title") or ""
    if any(hint in domain for hint in LOW_VALUE_SOURCE_HINTS):
        claim_tokens = _tokenize(claim) - GENERIC_SEARCH_TERMS
        result_tokens = _tokenize(f"{title} {result.get('snippet', '')}")
        return len(claim_tokens & result_tokens) < 4
    return False


def _result_relevance(claim: str, result: dict) -> dict:
    claim_tokens = _tokenize(claim)
    result_tokens = _tokenize(f"{result.get('title', '')} {result.get('snippet', '')}")
    meaningful_claim_tokens = claim_tokens - GENERIC_SEARCH_TERMS
    overlap = meaningful_claim_tokens & result_tokens
    required_terms = _domain_terms_for_claim(claim)
    required_tokens = _tokenize(" ".join(required_terms))
    required_hit = bool(required_tokens & result_tokens) if required_tokens else True
    coverage = round(len(overlap) / max(len(meaningful_claim_tokens), 1), 2)
    relevant = required_hit and (coverage >= 0.18 or len(overlap) >= 4)
    return {
        "coverage": coverage,
        "overlap": len(overlap),
        "required_hit": required_hit,
        "relevant": relevant and not _is_low_value_result(result, claim),
    }


def _filter_relevant_results(claim: str, results: list[dict]) -> list[dict]:
    filtered = []
    for result in results:
        relevance = _result_relevance(claim, result)
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


def _score_results(claim: str, results: list[dict]) -> dict:
    claim_tokens = _tokenize(claim) - GENERIC_SEARCH_TERMS
    if not claim_tokens:
        return {"coverage": 0, "trusted_count": 0, "top_overlap": 0}

    top_overlap = 0
    trusted_count = 0
    coverage_hits = set()
    for result in results:
        tokens = _tokenize(f"{result.get('title', '')} {result.get('snippet', '')}")
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
    }


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
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            return json.loads(match.group(0))
    raise ValueError("AI 核验返回不是有效 JSON")


def _default_model_config() -> tuple[str | None, str | None]:
    try:
        models = get_all_models()
    except Exception as exc:
        logger.warning(f"读取默认核验模型失败: {exc}")
        return None, None
    if not models:
        return None, None
    model = models[0]
    return str(model.get("model_name") or "") or None, str(model.get("provider_id") or "") or None


def _get_ai_verifier(model_name: str | None, provider_id: str | None):
    if not model_name or not provider_id:
        default_model_name, default_provider_id = _default_model_config()
        model_name = model_name or default_model_name
        provider_id = provider_id or default_provider_id
    if not model_name or not provider_id:
        return None
    provider = ProviderService.get_provider_by_id(provider_id)
    if not provider:
        return None
    logger.info(f"联网核验使用 AI 模型 provider_id={provider_id}, model={model_name}")
    return GPTFactory().from_config(ModelConfig(
        api_key=provider["api_key"],
        base_url=provider["base_url"],
        model_name=model_name,
        provider=provider["type"],
        name=provider["name"],
    ))


def _trim_context(context: str, limit: int = 6000) -> str:
    text = re.sub(r"\s+", " ", context or "").strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n...\n{tail}"


def _ai_build_context_profile(gpt, context: str) -> dict:
    if not gpt or not context:
        return {}
    prompt = f"""
你是视频内容理解助手。请从视频全文上下文中提炼事实核验所需背景。
输出 JSON，不要解释：
{{
  "topic": "视频主题",
  "domain": "所属领域",
  "key_terms": ["术语1", "术语2"],
  "aliases": {{"视频中的说法": "标准术语"}}
}}

视频上下文：
{_trim_context(context)}
""".strip()
    response = gpt._chat_completion_create([{"role": "user", "content": prompt}])
    try:
        payload = _json_from_ai_text(response.choices[0].message.content or "")
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        logger.warning(f"AI 上下文提炼失败: {exc}")
        return {}


def _ai_build_queries(gpt, claim: str, context_profile: dict | None = None, context: str = "") -> list[str]:
    profile_text = json.dumps(context_profile or {}, ensure_ascii=False)
    prompt = f"""
你是事实核验助手。请结合视频上下文，把下面的长观点改写成适合搜索引擎检索的查询词。
要求：
1. 保留实体、术语、年份、标准名称、定理/规则名称。
2. 如果观点里有视频内简称、口误或自造词，结合上下文改写为通用标准术语。
3. 删除修辞、泛词和无关解释。
4. 历史、军事、科技、学术主题必须同时给中文和英文查询；英文查询优先使用标准人名、武器名、事件名。
5. 不要输出解释，只输出 JSON。
JSON 格式：{{"queries":["英文 query","中文 query"],"query":"兜底 query","atomic_claim":"...","context_term":"..."}}

视频背景：
{profile_text}

视频上下文摘录：
{_trim_context(context, 2400)}

观点：
{claim}
""".strip()
    response = gpt._chat_completion_create([{"role": "user", "content": prompt}])
    payload = _json_from_ai_text(response.choices[0].message.content or "")
    raw_queries = payload.get("queries") or []
    if not isinstance(raw_queries, list):
        raw_queries = []
    queries = [str(item).strip() for item in raw_queries if str(item or "").strip()]
    query = str(payload.get("query") or "").strip()
    if query:
        queries.append(query)
    atomic_claim = str(payload.get("atomic_claim") or "").strip()
    queries.extend(_build_search_queries(atomic_claim or claim))
    deduped = []
    for item in queries:
        item = re.sub(r"\s+", " ", item).strip()
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:4] or _build_search_queries(atomic_claim or claim)


def _ai_build_query(gpt, claim: str, context_profile: dict | None = None, context: str = "") -> str:
    queries = _ai_build_queries(gpt, claim, context_profile=context_profile, context=context)
    return queries[0] if queries else _build_search_query(claim)


def _ai_judge_claim(gpt, claim: str, results: list[dict], context_profile: dict | None = None, context: str = "") -> dict:
    sources = [
        {
            "title": item.get("title", ""),
            "domain": item.get("domain", ""),
            "snippet": item.get("snippet", ""),
            "url": item.get("url", ""),
        }
        for item in results[:5]
    ]
    prompt = f"""
你是严谨的事实核验助手。请先结合视频上下文理解主张，再根据给定搜索结果判断。
判断外部事实时只能依据搜索结果；如果搜索结果不足以判断，必须输出 uncertain。
不要因为标题或词语相似就判定支持。

输出 JSON：
{{
  "verdict": "supported|refuted|uncertain",
  "reason": "一句中文理由",
  "confidence": 0-100,
  "useful_source_indexes": [0,1]
}}

待核验主张：
{claim}

视频背景：
{json.dumps(context_profile or {}, ensure_ascii=False)}

视频上下文摘录：
{_trim_context(context, 2400)}

搜索结果：
{json.dumps(sources, ensure_ascii=False)}
""".strip()
    response = gpt._chat_completion_create([{"role": "user", "content": prompt}])
    payload = _json_from_ai_text(response.choices[0].message.content or "")
    verdict = payload.get("verdict")
    if verdict not in {"supported", "refuted", "uncertain"}:
        verdict = "uncertain"
    indexes = payload.get("useful_source_indexes") or []
    useful_sources = []
    for idx in indexes:
        try:
            source = results[int(idx)]
            if source not in useful_sources:
                useful_sources.append(source)
        except Exception:
            continue
    return {
        "verdict": verdict,
        "reason": str(payload.get("reason") or "AI 未给出明确理由。")[:240],
        "confidence": max(0, min(100, int(payload.get("confidence") or 50))),
        "sources": useful_sources,
    }


def _ai_verdict_to_display(claim: dict, ai_result: dict) -> tuple[str, str, int]:
    verdict = ai_result.get("verdict")
    confidence = int(ai_result.get("confidence") or claim.get("confidence", 50) or 50)
    reason = ai_result.get("reason") or ""
    if verdict == "supported":
        return "AI 判断有外部佐证", reason, max(confidence, 72)
    if verdict == "refuted":
        return "AI 判断存在反证", reason, min(confidence, 35)
    return "AI 判断证据不足", reason, min(max(confidence, 40), 60)


def verify_claims_online(
    verification: dict,
    max_claims: int = 5,
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
            raw_results = search_web_multi(queries or [query], max_results=DEFAULT_MAX_RESULTS, claim=claim_text)
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
        if claim.get("verdict") in {"证据不足", "缺少来源", "需重点核实", "证据仍不足", "未找到外部证据"}
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
