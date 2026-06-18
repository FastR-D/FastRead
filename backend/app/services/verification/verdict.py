from __future__ import annotations

SUPPORTED_ONLINE_VERDICTS = {
    "找到权威相关资料",
    "找到相关资料",
    "AI 判断有外部佐证",
}

INSUFFICIENT_VERDICTS = {
    "证据不足",
    "缺少来源",
    "需重点核实",
    "证据仍不足",
    "未找到外部证据",
    "精确数字仍待核实",
    "相关资料未支持精确数字",
}


def online_verdict(claim: dict, results: list[dict], metrics: dict) -> tuple[str, str, int]:
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


def enforce_numeric_verdict(
    claim: dict,
    current_verdict: str,
    reason: str,
    confidence: int,
    metrics: dict,
) -> tuple[str, str, int]:
    if not metrics.get("numeric_claim") or metrics.get("numeric_match_count", 0) > 0:
        return current_verdict, reason, confidence
    if current_verdict not in SUPPORTED_ONLINE_VERDICTS:
        return current_verdict, reason, confidence

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


def summarize_claims(verification: dict, checked: int) -> dict:
    claims = list(verification.get("claims") or [])
    checked_claims = [claim for claim in claims if claim.get("online", {}).get("checked")]
    supported_count = sum(
        1
        for claim in checked_claims
        if claim.get("online", {}).get("verdict") in SUPPORTED_ONLINE_VERDICTS
    )
    refuted_count = sum(
        1
        for claim in checked_claims
        if claim.get("online", {}).get("verdict") == "AI 判断存在反证"
    )
    insufficient_count = sum(
        1
        for claim in claims
        if claim.get("verdict") in INSUFFICIENT_VERDICTS
    )

    base_score = int(verification.get("overall", {}).get("score") or 50)
    next_score = max(0, min(100, base_score + supported_count * 7))
    status = "联网核验完成" if checked else "保持离线核验"
    if checked and insufficient_count > supported_count:
        status = "仍需核实"
    if checked and supported_count >= max(1, checked // 2) and insufficient_count <= supported_count:
        status = "找到外部佐证"

    return {
        "supported_count": supported_count,
        "refuted_count": refuted_count,
        "score": next_score,
        "status": status,
        "summary": (
            f"已联网核验 {checked} 条主张，找到 {supported_count} 条外部佐证、{refuted_count} 条反证。"
            if checked
            else "联网核验未完成，当前结果仍基于离线文本证据判断。"
        ),
    }
