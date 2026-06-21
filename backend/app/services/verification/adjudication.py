from __future__ import annotations

from app.services.verification import evidence as evidence_service
from app.services.verification import source_intel
from app.services.verification.schemas import VERDICT_LABELS


def data_void_flags(sources: list[dict], evidence: list[dict], raw_result_count: int) -> list[str]:
    flags = []
    if raw_result_count < 3:
        flags.append("low_result_count")
    high_independent = source_intel.independent_source_count(sources, {"A", "B"})
    if high_independent == 0:
        flags.append("no_independent_authoritative_source")
    elif high_independent == 1:
        flags.append("low_independence")
    weak_sources = sum(1 for source in sources if source.get("trust_tier") in {"C", "D"})
    if weak_sources >= max(2, len(sources) // 2 + 1):
        flags.append("weak_sources_dominate")
    listicles = sum(1 for source in sources if "biased_listicle" in (source.get("risk_flags") or []))
    if listicles >= 2:
        flags.append("biased_listicles")
    reposts = sum(1 for source in sources if "press_release_repost" in (source.get("risk_flags") or []))
    if reposts >= 2:
        flags.append("press_release_repost")
    farms = sum(1 for source in sources if "content_farm_cluster" in (source.get("risk_flags") or []))
    if farms >= 2:
        flags.append("content_farm_cluster")
    missing_identity = sum(1 for source in sources if "missing_source_identity" in (source.get("risk_flags") or []))
    if missing_identity >= max(2, len(sources) // 2 + 1):
        flags.append("missing_source_identity")
    if not evidence:
        flags.append("no_body_evidence")
    return flags


def adjudicate_claim(
    claim: str,
    sources: list[dict],
    evidence: list[dict],
    raw_result_count: int,
    search_error: str = "",
) -> tuple[str, str, int, list[str], dict]:
    sources_by_url = {source.get("url") or "": source for source in sources}
    counts = evidence_service.evidence_counts(evidence, sources_by_url)
    source_flags = sorted({flag for source in sources for flag in (source.get("risk_flags") or [])})
    void_flags = data_void_flags(sources, evidence, raw_result_count)
    risk_flags = sorted(set(source_flags + void_flags))
    if search_error:
        risk_flags = sorted(set(risk_flags + ["search_unavailable"]))

    if search_error and not sources:
        return (
            "data_void",
            "联网检索不可用，且没有可抓取正文证据；降级模式不能给出支持结论。",
            38,
            risk_flags,
            counts,
        )

    high_support = counts["high_support_independent"]
    high_refute = counts["high_refute_independent"]
    high_independent = source_intel.independent_source_count(sources, {"A", "B"})

    if (
        "blocked_domain" in source_flags
        or ("prompt_injection" in source_flags and high_independent == 0)
        or ("fake_authority" in source_flags and high_independent == 0)
    ):
        return (
            "source_risk",
            "检索结果存在投毒、伪权威或指令注入风险，且没有足够的独立高可信正文证据覆盖主张。",
            35,
            risk_flags,
            counts,
        )

    if high_refute > 0 and high_support == 0:
        return (
            "refuted",
            "高可信来源正文中出现与主张核心数字、主体、时间、地点或关系相冲突的证据。",
            min(92, 70 + high_refute * 10),
            risk_flags,
            counts,
        )

    if high_support > 0 and high_refute > 0:
        return (
            "mixed",
            "高可信来源同时出现支持和反驳证据，可能存在统计口径、地域、时间范围或定义差异。",
            64,
            risk_flags,
            counts,
        )

    if high_support >= 2:
        return (
            "supported",
            "至少两个独立高可信来源的正文证据覆盖主张核心元素，且没有同等级反证。",
            min(95, 78 + high_support * 6),
            risk_flags,
            counts,
        )

    if high_support == 1 and high_independent >= 2 and counts["support"] >= 2:
        return (
            "supported",
            "一个高可信正文证据与其他独立相关来源相互印证，且没有同等级反证。",
            78,
            risk_flags,
            counts,
        )

    if any(flag in void_flags for flag in ("low_result_count", "no_independent_authoritative_source", "weak_sources_dominate")):
        return (
            "data_void",
            "结果数量、来源独立性或来源等级不足，弱来源/SEO/转载内容占主导；不能给出支持结论。",
            42,
            risk_flags,
            counts,
        )

    return (
        "insufficient",
        "检索到相关资料，但正文证据没有覆盖主张核心元素，或只有单一/低等级来源。",
        52,
        risk_flags,
        counts,
    )


def legacy_display(verdict: str) -> str:
    return VERDICT_LABELS.get(verdict, verdict)
