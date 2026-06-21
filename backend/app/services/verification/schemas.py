from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal


TrustTier = Literal["A", "B", "C", "D", "blocked"]
VerificationVerdict = Literal[
    "supported",
    "refuted",
    "mixed",
    "insufficient",
    "data_void",
    "source_risk",
]
EvidenceStance = Literal["support", "refute", "context"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ClaimFacts:
    entities: list[str] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    numbers: list[dict[str, Any]] = field(default_factory=list)
    comparisons: list[str] = field(default_factory=list)
    domain_type: str = "general"
    risk_topics: list[str] = field(default_factory=list)


@dataclass
class VerificationSource:
    url: str
    source_id: str = ""
    canonical_url: str = ""
    domain: str = ""
    title: str = ""
    publisher: str = ""
    author: str = ""
    published_at: str = ""
    retrieved_at: str = ""
    source_type: str = "web"
    trust_tier: TrustTier = "D"
    trust_reasons: list[str] = field(default_factory=list)
    independence_group: str = ""
    content_hash: str = ""
    fetch_status: str = "not_fetched"
    snippet: str = ""
    trusted: bool = False


@dataclass
class VerificationEvidence:
    source_url: str
    passage: str
    stance: EvidenceStance
    evidence_id: str = ""
    claim_element: str = "overall"
    exact_value: str = ""
    unit: str = ""
    page_offsets: dict[str, int] = field(default_factory=dict)
    confidence: int = 0
    extraction_method: str = "rules"


@dataclass
class ClaimVerificationResult:
    claim_id: str
    atomic_claim: str
    claim_facts: ClaimFacts
    verdict: VerificationVerdict
    reason: str
    confidence: int
    sources: list[VerificationSource] = field(default_factory=list)
    evidence: list[VerificationEvidence] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)


def to_plain_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain_dict(item) for key, item in value.items()}
    return value


VERDICT_LABELS: dict[str, str] = {
    "supported": "高可信证据支持",
    "refuted": "高可信证据反驳",
    "mixed": "证据口径冲突",
    "insufficient": "证据不足",
    "data_void": "数据荒漠",
    "source_risk": "信源风险",
}
