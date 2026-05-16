from __future__ import annotations

import os
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.utils.logger import get_logger

logger = get_logger(__name__)

SEARCH_TIMEOUT = float(os.getenv("ONLINE_VERIFY_TIMEOUT", "8"))
DEFAULT_MAX_RESULTS = int(os.getenv("ONLINE_VERIFY_RESULTS", "5"))

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
    "百科",
)

KEEP_CHINESE_TERMS = {"边际成本", "边际效用", "价格歧视", "集体行动", "隐性成本", "激励机制"}


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


def _is_trusted_source(title: str, url: str) -> bool:
    domain = _domain(url)
    title_text = title or ""
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
        results.append({
            "title": title[:160],
            "url": url,
            "domain": _domain(url),
            "snippet": snippet[:260],
            "trusted": _is_trusted_source(title, url),
        })
        if len(results) >= max_results:
            break
    return results


def search_web(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> list[dict]:
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


def _build_search_query(claim: str) -> str:
    text = re.sub(r"^\s*(引申|应用|经济学解释|总结|核心观点|结论)[：:]\s*", "", claim or "")
    text = re.sub(r"[“”\"'`]", "", text)
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
    }
    terms = []
    for part in parts:
        item = part.strip()
        if not item or item in stop_words:
            continue
        if len(item) > 14:
            item = item[:14]
        if re.fullmatch(r"[a-zA-Z]{1,3}", item):
            continue
        expanded = [item]
        chinese_only = "".join(re.findall(r"[\u4e00-\u9fff]", item))
        if item in KEEP_CHINESE_TERMS:
            expanded = [item]
        elif len(chinese_only) > 3:
            expanded = [chinese_only[i:i + 2] for i in range(0, len(chinese_only), 2)]
        for term in expanded:
            if len(term) >= 2 and term not in terms and term not in stop_words:
                terms.append(term)
            if len(terms) >= 10:
                break
        if len(terms) >= 8:
            break
    return " ".join(terms) or (claim or "")[:60]


def _score_results(claim: str, results: list[dict]) -> dict:
    claim_tokens = _tokenize(claim)
    if not claim_tokens:
        return {"coverage": 0, "trusted_count": 0, "top_overlap": 0}

    top_overlap = 0
    trusted_count = 0
    coverage_hits = set()
    for result in results:
        text = f"{result.get('title', '')} {result.get('snippet', '')}"
        tokens = _tokenize(text)
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


def verify_claims_online(verification: dict, max_claims: int = 5) -> dict:
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

    for claim in selected:
        claim_text = claim.get("claim") or ""
        if not claim_text:
            continue
        try:
            query = _build_search_query(claim_text)
            results = search_web(query, max_results=DEFAULT_MAX_RESULTS)
            metrics = _score_results(claim_text, results)
            verdict, reason, confidence = _online_verdict(claim, results, metrics)
            target = by_claim.get(claim_text)
            if not target:
                continue
            target["online"] = {
                "checked": True,
                "query": query,
                "verdict": verdict,
                "reason": reason,
                "confidence": confidence,
                "metrics": metrics,
                "sources": results,
            }
            target["verdict"] = verdict
            target["reason"] = reason
            target["confidence"] = confidence
            checked += 1
        except Exception as exc:
            logger.warning(f"联网核验失败: {claim_text[:60]} {exc}")
            errors.append(str(exc))

    checked_claims = [claim for claim in claims if claim.get("online", {}).get("checked")]
    supported_count = sum(
        1
        for claim in checked_claims
        if claim.get("online", {}).get("verdict") in {"找到权威相关资料", "找到相关资料"}
    )
    insufficient_count = sum(
        1
        for claim in claims
        if claim.get("verdict") in {"证据不足", "缺少来源", "需重点核实", "证据仍不足", "未找到外部证据"}
    )

    base_score = int(verification.get("overall", {}).get("score") or 50)
    next_score = base_score + supported_count * 7
    next_score = max(0, min(100, next_score))
    status = "联网核验完成" if checked else "联网核验失败"
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
    }
    verification["overall"] = {
        **(verification.get("overall") or {}),
        "status": status,
        "score": next_score,
        "summary": f"已联网核验 {checked} 条主张，找到 {supported_count} 条相关外部资料。",
        "note": "联网核验基于搜索结果标题、摘要和来源域名做证据扫描，不等同于人工事实核查。",
    }
    verification["claims"] = claims
    return verification
