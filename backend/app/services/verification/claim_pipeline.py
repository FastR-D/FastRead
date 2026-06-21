from __future__ import annotations

import re

from app.services.verification import numeric_evidence
from app.services.verification.schemas import ClaimFacts


DOMAIN_HINTS = {
    "science": ("研究", "论文", "实验", "蛋白", "protein", "gene", "cell", "clinical", "study"),
    "finance": ("财报", "营收", "利润", "市值", "股价", "earnings", "revenue", "profit"),
    "law": ("法律", "法规", "法院", "判决", "监管", "regulation", "court", "sec"),
    "public_policy": ("政府", "统计", "人口", "财政", "政策", "census", "statistic", "policy"),
    "health": ("疾病", "药", "治疗", "疫苗", "患者", "health", "disease", "vaccine"),
}

HIGH_RISK_HINTS = (
    "致癌",
    "死亡",
    "疗效",
    "投资",
    "收益",
    "违法",
    "战争",
    "灾害",
    "死亡率",
    "cancer",
    "death",
    "investment",
    "illegal",
)


def split_atomic_claims(text: str, max_claims: int = 50) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    parts = re.split(r"(?:[。！？!?；;]\s*|\n+|(?<=\.)\s+(?=[A-Z0-9]))", cleaned)
    claims = []
    for part in parts:
        item = re.sub(r"^[\-*#>\s]+", "", part).strip()
        if len(item) < 6:
            continue
        if item not in claims:
            claims.append(item[:500])
        if len(claims) >= max_claims:
            break
    return claims


def extract_claim_facts(claim: str) -> ClaimFacts:
    text = claim or ""
    numbers = numeric_evidence.extract_numeric_constraints(text)
    times = []
    for match in re.finditer(r"(?:18|19|20)\d{2}\s*年?|(?:Q[1-4]|[一二三四]季度)", text, re.I):
        value = match.group(0).strip()
        if value not in times:
            times.append(value)

    locations = []
    for match in re.finditer(r"(中国|美国|日本|欧盟|英国|北京|上海|全球|亚洲|欧洲|United States|China|Japan|EU)", text, re.I):
        value = match.group(0)
        if value not in locations:
            locations.append(value)

    entities = []
    for match in re.finditer(r"[A-Z][A-Za-z0-9&.\-]{2,}(?:\s+[A-Z][A-Za-z0-9&.\-]{2,}){0,3}|[\u4e00-\u9fff]{2,12}", text):
        value = match.group(0).strip()
        if value in locations or value in times:
            continue
        if value not in entities:
            entities.append(value)
        if len(entities) >= 12:
            break

    comparisons = []
    for match in re.finditer(r"(超过|高于|低于|不超过|至少|最多|more than|less than|higher than|lower than)", text, re.I):
        value = match.group(0)
        if value not in comparisons:
            comparisons.append(value)

    lower = text.lower()
    domain_type = "general"
    for name, hints in DOMAIN_HINTS.items():
        if any(hint in lower or hint in text for hint in hints):
            domain_type = name
            break

    risk_topics = [hint for hint in HIGH_RISK_HINTS if hint in lower or hint in text]
    if numbers and "numeric" not in risk_topics:
        risk_topics.append("numeric")

    return ClaimFacts(
        entities=entities,
        times=times,
        locations=locations,
        numbers=numbers,
        comparisons=comparisons,
        domain_type=domain_type,
        risk_topics=risk_topics,
    )


def sort_claims_by_verification_risk(claims: list[dict], max_claims: int) -> list[dict]:
    def score(item: dict) -> int:
        text = item.get("claim") or item.get("text") or ""
        facts = extract_claim_facts(text)
        return (
            int(item.get("priority", 0)) * 2
            + len(facts.risk_topics) * 8
            + len(facts.numbers) * 6
            + len(facts.times) * 2
            + (5 if facts.domain_type in {"health", "finance", "law", "public_policy"} else 0)
        )

    return sorted(claims, key=score, reverse=True)[:max(1, max_claims)]
