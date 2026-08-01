from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from app.services.academic_evidence import assess_academic_identity
from app.services.verification import source_registry
from app.services.verification.text_utils import domain as parse_domain, strip_html


A_TIER_DOMAIN_HINTS = (
    ".gov",
    "gov.cn",
    "stats.gov.cn",
    "sec.gov",
    "europa.eu",
    "who.int",
    "un.org",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "doi.org",
    "court",
    "supreme",
)

B_TIER_DOMAIN_HINTS = (
    ".edu",
    "nature.com",
    "science.org",
    "springer.com",
    "sciencedirect.com",
    "wiley.com",
    "tandfonline.com",
    "frontiersin.org",
    "acs.org",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "nytimes.com",
    "economist.com",
    "caixin.com",
    "thepaper.cn",
)

C_TIER_DOMAIN_HINTS = (
    "wikipedia.org",
    "baike.baidu.com",
    "baike.com",
    "medium.com",
    "substack.com",
    "blog",
)

D_TIER_DOMAIN_HINTS = (
    "zhihu.com",
    "weibo.com",
    "douyin.com",
    "toutiao.com",
    "bilibili.com",
    "reddit.com",
    "quora.com",
    "sohu.com",
    "163.com",
    "rank",
    "top10",
)

BLOCKED_DOMAIN_HINTS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
)

LISTICLE_TITLE_HINTS = (
    "十大",
    "排行榜",
    "榜单",
    "推荐",
    "盘点",
    "top 10",
    "best ",
    "ranking",
)

PROMPT_INJECTION_PATTERNS = (
    r"ignore (all )?(previous|prior) (instructions|prompt)",
    r"disregard (all )?(previous|prior) (instructions|prompt)",
    r"system prompt",
    r"developer message",
    r"你(?:必须|需要)忽略(?:之前|以上)指令",
    r"忽略(?:所有|之前|以上)指令",
    r"作为(?:ai|语言模型).*?(执行|输出)",
)


def normalize_canonical_url(url: str) -> str:
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return url or ""
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(fragment="", query="", path=path).geturl()


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", strip_html(text or "")).strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized[:20000].encode("utf-8", errors="ignore")).hexdigest()[:16]


def source_id_for(url: str, canonical_url: str = "", text_hash: str = "") -> str:
    stable = "|".join([normalize_canonical_url(canonical_url or url), text_hash or ""])
    digest = hashlib.sha1(stable.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"src-{digest}"


def independence_group(url: str, canonical_url: str = "", publisher: str = "", text_hash: str = "") -> str:
    base = parse_domain(canonical_url or url)
    publisher_key = re.sub(r"\W+", "-", (publisher or "").strip().lower()).strip("-")
    if text_hash:
        return f"{base}:{text_hash}"
    return publisher_key or base or normalize_canonical_url(canonical_url or url)


def detect_prompt_injection(text: str) -> list[str]:
    lower = (text or "").lower()
    flags = []
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lower, re.I | re.S):
            flags.append("prompt_injection")
            break
    return flags


def detect_source_risks(source: dict, text: str = "") -> list[str]:
    title = source.get("title") or ""
    source_domain = source.get("domain") or parse_domain(source.get("url") or "")
    flags = []
    if any(hint in source_domain for hint in BLOCKED_DOMAIN_HINTS) or source_domain in source_registry.BLOCKED_DOMAINS:
        flags.append("blocked_domain")
    if source.get("fake_authority"):
        flags.append("fake_authority")
    if source.get("canonical_anomaly"):
        flags.append("canonical_anomaly")
    if source.get("redirect_anomaly"):
        flags.append("redirect_anomaly")
    risky_flag = source_registry.risky_domain_flag(source_domain)
    if risky_flag:
        flags.append(risky_flag)
    if source.get("missing_source_identity"):
        flags.append("missing_source_identity")
    if source.get("missing_publisher"):
        flags.append("missing_publisher")
    if source.get("missing_author"):
        flags.append("missing_author")
    if source.get("missing_published_date"):
        flags.append("missing_published_date")
    if any(hint in (title or "").lower() for hint in LISTICLE_TITLE_HINTS):
        flags.append("biased_listicle")
    if source.get("fetch_status") in {"failed", "blocked", "empty"}:
        flags.append("unfetchable")
    flags.extend(detect_prompt_injection(text))
    return sorted(set(flags))


def classify_source(result: dict, fetched: dict | None = None) -> dict:
    fetched = fetched or {}
    original_url = result.get("url") or ""
    url = fetched.get("url") or result.get("url") or ""
    canonical_url = normalize_canonical_url(fetched.get("canonical_url") or url)
    source_domain = parse_domain(canonical_url or url)
    fetched_domain = parse_domain(url)
    original_domain = parse_domain(original_url)
    title = fetched.get("title") or result.get("title") or ""
    text = fetched.get("text") or ""
    fetch_status = fetched.get("fetch_status") or "not_fetched"
    publisher = fetched.get("publisher") or result.get("publisher") or ""
    text_hash = content_hash(text)
    registry_match = source_registry.lookup_domain(source_domain)
    fake_authority = source_registry.detect_fake_authority(source_domain, title, publisher)
    canonical_anomaly = source_registry.detect_canonical_anomaly(original_url, url, canonical_url)
    redirect_anomaly = bool(
        original_domain
        and fetched_domain
        and not source_registry.domain_matches(fetched_domain, original_domain)
        and not source_registry.domain_matches(original_domain, fetched_domain)
    )
    author = fetched.get("author") or result.get("author") or ""
    published_at = fetched.get("published_at") or result.get("published_at") or ""
    fetched_body = fetch_status in {"ok", "pdf_ok"}
    missing_publisher = bool(fetched_body and not publisher)
    missing_author = bool(fetched_body and not author)
    missing_published_date = bool(fetched_body and not published_at)
    missing_source_identity = bool(missing_publisher and missing_author and missing_published_date)
    academic = assess_academic_identity({**result, **fetched, "canonical_url": canonical_url, "url": url})

    tier = "D"
    reasons = []
    if any(hint in source_domain for hint in BLOCKED_DOMAIN_HINTS):
        tier = "blocked"
        reasons.append("blocked or local domain")
    elif registry_match:
        tier = registry_match["tier"]
        reasons.append(f"source registry matched {registry_match['domain']} ({registry_match['label']})")
    elif any(hint in source_domain for hint in A_TIER_DOMAIN_HINTS):
        tier = "A"
        reasons.append("primary official, regulator, statistics, court, or original research domain")
    elif any(hint in source_domain for hint in B_TIER_DOMAIN_HINTS):
        tier = "B"
        reasons.append("recognized institution, publisher, database, or mainstream reporting domain")
    elif any(hint in source_domain for hint in C_TIER_DOMAIN_HINTS):
        tier = "C"
        reasons.append("tertiary, encyclopedia, blog, or republished source")
    elif result.get("trusted"):
        tier = "B"
        reasons.append("legacy trusted heuristic matched")
    else:
        reasons.append("weak or unverified source identity")

    if any(hint in source_domain for hint in D_TIER_DOMAIN_HINTS):
        tier = "D" if tier != "blocked" else "blocked"
        reasons.append("forum, social, SEO, portal, or ranking/listicle domain")

    if fake_authority:
        tier = "D" if tier != "blocked" else "blocked"
        reasons.append("domain or publisher text resembles a known authority but is not in the source registry")
    if canonical_anomaly:
        reasons.append("canonical or fetched URL domain diverges from the search result domain")

    if fetch_status in {"failed", "empty", "blocked"} and tier in {"A", "B"}:
        reasons.append("source identity is strong but body was not fetched; cannot support claims alone")
    if missing_source_identity:
        reasons.append("fetched body lacks publisher, author, and published date metadata")
    elif missing_published_date:
        reasons.append("fetched body lacks published date metadata")

    risk_flags = detect_source_risks({
        **result,
        "domain": source_domain,
        "fetch_status": fetch_status,
        "fake_authority": fake_authority,
        "canonical_anomaly": canonical_anomaly,
        "redirect_anomaly": redirect_anomaly,
        "missing_source_identity": missing_source_identity,
        "missing_publisher": missing_publisher,
        "missing_author": missing_author,
        "missing_published_date": missing_published_date,
    }, text)
    if academic["level"] == "U":
        risk_flags.append("academic_identity_incomplete")
    if academic["publication_status"] == "retracted":
        risk_flags.append("retracted_or_withdrawn")

    return {
        "source_id": source_id_for(url, canonical_url, text_hash),
        "url": url,
        "canonical_url": canonical_url,
        "domain": source_domain,
        "title": title[:200],
        "publisher": publisher,
        "author": author,
        "authors": fetched.get("authors") or result.get("authors") or ([author] if author else []),
        "published_at": published_at,
        "doi": academic.get("doi") or "",
        "venue": academic.get("venue") or {},
        "pdf_url": fetched.get("pdf_url") or result.get("pdf_url") or "",
        "academic": academic,
        "retrieved_at": fetched.get("retrieved_at") or "",
        "source_type": fetched.get("source_type") or "web",
        "redirect_chain": fetched.get("redirect_chain") or [],
        "page_spans": fetched.get("page_spans") or [],
        "trust_tier": tier,
        "trust_reasons": reasons,
        "independence_group": independence_group(url, canonical_url, publisher, text_hash),
        "content_hash": text_hash,
        "fetch_status": fetch_status,
        "snippet": result.get("snippet") or "",
        "trusted": tier in {"A", "B"},
        "risk_flags": sorted(set(risk_flags)),
    }


def annotate_cross_source_risks(sources: list[dict]) -> list[dict]:
    hash_domains: dict[str, set[str]] = {}
    content_farm_count = 0
    listicle_count = 0
    for source in sources:
        text_hash = source.get("content_hash") or ""
        if text_hash:
            hash_domains.setdefault(text_hash, set()).add(source.get("domain") or "")
        flags = set(source.get("risk_flags") or [])
        if "content_farm" in flags:
            content_farm_count += 1
        if "biased_listicle" in flags:
            listicle_count += 1

    copied_hashes = {
        text_hash
        for text_hash, domains in hash_domains.items()
        if text_hash and len({domain for domain in domains if domain}) >= 2
    }
    farm_cluster = content_farm_count >= 2 or (content_farm_count >= 1 and listicle_count >= 2)
    annotated = []
    for source in sources:
        item = dict(source)
        flags = set(item.get("risk_flags") or [])
        if item.get("content_hash") in copied_hashes and item.get("trust_tier") in {"C", "D"}:
            flags.add("press_release_repost")
        if farm_cluster and ("content_farm" in flags or "biased_listicle" in flags):
            flags.add("content_farm_cluster")
        item["risk_flags"] = sorted(flags)
        annotated.append(item)
    return annotated


def independent_source_count(sources: list[dict], tiers: set[str] | None = None) -> int:
    groups = set()
    tiers = tiers or {"A", "B"}
    for source in sources:
        if source.get("trust_tier") not in tiers:
            continue
        if source.get("fetch_status") not in {"ok", "pdf_ok"}:
            continue
        if "missing_source_identity" in (source.get("risk_flags") or []):
            continue
        groups.add(source.get("independence_group") or source.get("domain") or source.get("url"))
    return len(groups)
