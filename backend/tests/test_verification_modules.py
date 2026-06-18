from app.services.verification import numeric_evidence
from app.services.verification import query_builder
from app.services.verification import relevance
from app.services.verification import search_orchestrator
from app.services.verification import verdict


def test_query_builder_keeps_scientific_numeric_academic_queries():
    queries = query_builder.build_search_queries("鸡蛋中含有超过1500种独特蛋白质")

    assert '"chicken egg" "1500" proteins proteome' in queries
    assert '"Egg White and Yolk Protein Atlas"' in queries
    assert len(queries) <= 4


def test_numeric_evidence_detects_related_conflict():
    metrics = numeric_evidence.score_numeric_evidence(
        "鸡蛋中含有超过1500种独特蛋白质",
        [
            {
                "title": "Egg White and Yolk Protein Atlas",
                "url": "https://pubmed.ncbi.nlm.nih.gov/123456/",
                "domain": "pubmed.ncbi.nlm.nih.gov",
                "snippet": "The chicken egg atlas reports 1392 protein entries across egg white and yolk.",
                "trusted": True,
            }
        ],
    )

    assert metrics["numeric_claim"]
    assert metrics["numeric_match_count"] == 0
    assert metrics["numeric_conflict_count"] > 0


def test_relevance_allows_trusted_english_scientific_result_for_chinese_claim():
    result = {
        "title": "Egg White and Yolk Protein Atlas",
        "url": "https://pubmed.ncbi.nlm.nih.gov/123456/",
        "domain": "pubmed.ncbi.nlm.nih.gov",
        "snippet": "A chicken egg proteome resource with protein entries.",
        "trusted": True,
    }

    score = relevance.result_relevance("鸡蛋中含有超过1500种独特蛋白质", result)

    assert score["relevant"]


def test_verdict_rejects_numeric_claim_without_matching_number():
    claim = {"claim": "鸡蛋中含有超过1500种独特蛋白质", "confidence": 50}
    metrics = {
        "coverage": 0.8,
        "trusted_count": 1,
        "top_overlap": 6,
        "numeric_claim": True,
        "numeric_match_count": 0,
        "numeric_conflict_count": 1,
    }

    current_verdict, reason, confidence = verdict.online_verdict(claim, [{"trusted": True}], metrics)

    assert current_verdict == "相关资料未支持精确数字"
    assert "数值" in reason
    assert confidence <= 58


def test_search_orchestrator_uses_quality_supplement_for_weak_result(monkeypatch):
    weak_result = {
        "title": "鸡蛋 1500种 独特 蛋白质",
        "url": "https://www.zhihu.com/question/1",
        "snippet": "鸡蛋 1500种 独特 蛋白质",
        "trusted": False,
    }
    academic_result = {
        "title": "鸡蛋 1500种 独特 蛋白质 研究",
        "url": "https://example.edu/paper",
        "snippet": "鸡蛋 1500种 独特 蛋白质 研究",
        "trusted": True,
    }

    monkeypatch.setattr(
        search_orchestrator.search_providers,
        "quality_supplement_providers",
        lambda used: ["bing_cn"],
    )
    monkeypatch.setattr(
        search_orchestrator.search_providers,
        "domestic_supplement_providers",
        lambda: [],
    )

    provider_trace = []
    results = search_orchestrator.search_web_multi(
        ["鸡蛋 1500种 蛋白质"],
        claim="鸡蛋中含有超过1500种独特蛋白质",
        provider_trace=provider_trace,
        search_with_provider_fn=lambda _query, _limit: ([weak_result], "bing_academic"),
        provider_results_fn=lambda provider, _query, _limit: [academic_result] if provider == "bing_cn" else [],
    )

    assert results == [weak_result, academic_result]
    assert provider_trace == ["bing_academic", "bing_cn"]
