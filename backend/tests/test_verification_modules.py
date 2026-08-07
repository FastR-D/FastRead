from app.services.verification import evidence
from app.services.verification import fetching
from app.services.verification import numeric_evidence
from app.services.verification import query_builder
from app.services.verification import relevance
from app.services.verification import search_orchestrator
from app.services.verification import source_intel
from app.services.verification import source_registry
from app.services.verification import verdict


def test_query_builder_keeps_scientific_numeric_academic_queries():
    queries = query_builder.build_search_queries("鸡蛋中含有超过1500种独特蛋白质")

    assert '"chicken egg" "1500" proteins proteome' in queries
    assert '"Egg White and Yolk Protein Atlas"' in queries
    assert len(queries) <= 4


def test_query_builder_builds_geo_language_variants():
    variants = query_builder.build_geo_language_queries(
        "2023年7月，IARC将阿斯巴甜列为2B类可能对人类致癌。"
    )

    assert "zh_cn" in variants
    assert "en_global" in variants
    assert any("世界卫生组织" in query or "IARC" in query for query in variants["zh_cn"])
    assert any("WHO" in query or "official source" in query for query in variants["en_global"])


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


def test_numeric_evidence_ignores_iarc_group_codes_as_numeric_constraints():
    metrics = numeric_evidence.score_numeric_evidence(
        "2023年7月，IARC将阿斯巴甜列为2B类可能对人类致癌，JECFA维持每日允许摄入量40 mg/kg体重。",
        [
            {
                "title": "Aspartame hazard and risk assessment results released",
                "url": "https://www.who.int/news/item/14-07-2023-aspartame-hazard-and-risk-assessment-results-released",
                "domain": "who.int",
                "snippet": "IARC classified aspartame as possibly carcinogenic to humans (IARC Group 2B) and JECFA reaffirmed the acceptable daily intake of 40 mg/kg body weight.",
                "trusted": True,
            }
        ],
    )

    assert metrics["numeric_claim"]
    assert metrics["numeric_conflict_count"] == 0
    assert metrics["numeric_match_count"] > 0


def test_numeric_evidence_treats_dose_ranges_as_one_comparable_value():
    constraints = numeric_evidence.extract_numeric_constraints("JECFA维持每日允许摄入量40 mg/kg体重")
    passage_mentions = numeric_evidence.extract_numeric_mentions(
        "JECFA reaffirmed the acceptable daily intake (ADI) of 0-40 mg/kg body weight for aspartame."
    )

    assert constraints
    assert len(passage_mentions) == 1
    assert passage_mentions[0]["op"] == "range"
    assert numeric_evidence.numeric_supports(constraints[0], passage_mentions[0])
    assert not numeric_evidence.numeric_conflicts(constraints[0], passage_mentions[0])


def test_numeric_evidence_converts_chinese_and_english_population_units():
    constraints = numeric_evidence.extract_numeric_constraints("该国人口超过14亿人")
    billion_mentions = numeric_evidence.extract_numeric_mentions(
        "The country's population is more than 1.4 billion people."
    )
    million_mentions = numeric_evidence.extract_numeric_mentions(
        "The country's population reached about 1,400 million people."
    )
    conflict_mentions = numeric_evidence.extract_numeric_mentions(
        "The country's population is about 140 million people."
    )

    assert constraints
    assert billion_mentions
    assert million_mentions
    assert conflict_mentions
    assert constraints[0]["value"] == 1_400_000_000
    assert billion_mentions[0]["value"] == 1_400_000_000
    assert million_mentions[0]["value"] == 1_400_000_000
    assert numeric_evidence.numeric_context_related(constraints[0], billion_mentions[0])
    assert numeric_evidence.numeric_supports(constraints[0], billion_mentions[0])
    assert numeric_evidence.numeric_supports(constraints[0], million_mentions[0])
    assert numeric_evidence.numeric_conflicts(constraints[0], conflict_mentions[0])


def test_numeric_evidence_scores_unit_converted_population_support():
    metrics = numeric_evidence.score_numeric_evidence(
        "该国人口超过14亿人",
        [
            {
                "title": "Population statistics",
                "url": "https://stats.example/report",
                "domain": "stats.example",
                "snippet": "The country's population is more than 1.4 billion people according to the census.",
                "trusted": True,
            }
        ],
    )

    assert metrics["numeric_claim"]
    assert metrics["numeric_match_count"] == 1
    assert metrics["numeric_conflict_count"] == 0


def test_numeric_evidence_allows_source_approximation_without_false_conflict():
    constraints = numeric_evidence.extract_numeric_constraints("鸡蛋中含有1500种独特蛋白质")
    close_mentions = numeric_evidence.extract_numeric_mentions(
        "The chicken egg proteome contains about 1,430 protein entries."
    )
    gray_mentions = numeric_evidence.extract_numeric_mentions(
        "The chicken egg proteome contains about 1,200 protein entries."
    )
    far_mentions = numeric_evidence.extract_numeric_mentions(
        "The chicken egg proteome contains about 1,050 protein entries."
    )

    assert constraints
    assert close_mentions
    assert gray_mentions
    assert far_mentions
    assert close_mentions[0]["op"] == "approx"
    assert numeric_evidence.numeric_context_related(constraints[0], close_mentions[0])
    assert numeric_evidence.numeric_supports(constraints[0], close_mentions[0])
    assert not numeric_evidence.numeric_conflicts(constraints[0], close_mentions[0])
    assert not numeric_evidence.numeric_supports(constraints[0], gray_mentions[0])
    assert not numeric_evidence.numeric_conflicts(constraints[0], gray_mentions[0])
    assert numeric_evidence.numeric_conflicts(constraints[0], far_mentions[0])


def test_numeric_evidence_scores_source_approximation_support():
    metrics = numeric_evidence.score_numeric_evidence(
        "鸡蛋中含有1500种独特蛋白质",
        [
            {
                "title": "Chicken egg proteome",
                "url": "https://example.edu/egg-proteome",
                "domain": "example.edu",
                "snippet": "The chicken egg proteome contains about 1,430 protein entries.",
                "trusted": True,
            }
        ],
    )

    assert metrics["numeric_claim"]
    assert metrics["numeric_match_count"] == 1
    assert metrics["numeric_conflict_count"] == 0


def test_numeric_evidence_ignores_population_numbers_with_different_statistical_scope():
    constraints = numeric_evidence.extract_numeric_constraints("中国人口超过14亿人")
    china_mentions = numeric_evidence.extract_numeric_mentions(
        "China's population is more than 1.4 billion people."
    )
    global_mentions = numeric_evidence.extract_numeric_mentions(
        "The global population is about 8 billion people."
    )

    assert constraints
    assert china_mentions
    assert global_mentions
    assert numeric_evidence.statistical_scope(constraints[0]["context"]) == "china"
    assert numeric_evidence.statistical_scope(china_mentions[0]["context"]) == "china"
    assert numeric_evidence.statistical_scope(global_mentions[0]["context"]) == "global"
    assert numeric_evidence.numeric_context_related(constraints[0], china_mentions[0])
    assert numeric_evidence.numeric_supports(constraints[0], china_mentions[0])
    assert not numeric_evidence.numeric_context_related(constraints[0], global_mentions[0])


def test_numeric_evidence_scores_scope_mismatch_as_not_comparable():
    metrics = numeric_evidence.score_numeric_evidence(
        "中国人口超过14亿人",
        [
            {
                "title": "World population statistics",
                "url": "https://stats.example/world",
                "domain": "stats.example",
                "snippet": "The global population is about 8 billion people.",
                "trusted": True,
            }
        ],
    )

    assert metrics["numeric_claim"]
    assert metrics["numeric_comparable_count"] == 0
    assert metrics["numeric_match_count"] == 0
    assert metrics["numeric_conflict_count"] == 0


def test_numeric_evidence_ignores_contact_numbers_in_body_passages():
    mentions = numeric_evidence.extract_numeric_mentions(
        "Media Contacts Veronique Terrasse Communications Officer, IARC Communications Group Telephone: +33 472 738 366 Mobile: +33 645 284 952 Email: media@example.org"
    )

    assert mentions == []


def test_numeric_evidence_does_not_compare_dose_with_navigation_counts():
    constraints = numeric_evidence.extract_numeric_constraints("JECFA维持每日允许摄入量40 mg/kg体重")
    passage_mentions = numeric_evidence.extract_numeric_mentions(
        "IARC@60 Cancer Topics. IARC Monographs volume 134 evaluations. 17.06.2026 Read more."
    )

    assert constraints
    assert not any(numeric_evidence.numeric_context_related(constraints[0], mention) for mention in passage_mentions)


def test_evidence_refutes_wrong_iarc_classification_with_body_text():
    source = {"url": "https://www.who.int/aspartame", "trust_tier": "A", "fetch_status": "ok"}
    extracted = evidence.extract_evidence_for_claim(
        "世界卫生组织在2023年宣布阿斯巴甜被列为IARC 1类确定致癌物。",
        source,
        "IARC classified aspartame as possibly carcinogenic to humans (IARC Group 2B).",
    )

    assert extracted
    assert extracted[0]["stance"] == "refute"
    assert extracted[0]["exact_value"] == "2b"
    assert extracted[0]["evidence_id"].startswith("ev-")


def test_evidence_maps_offsets_to_pdf_pages():
    text, page_spans = fetching._pdf_text_with_spans([
        "Page one unrelated.",
        "IARC classified aspartame as possibly carcinogenic to humans (IARC Group 2B).",
    ])
    source = {
        "url": "https://example.org/report.pdf",
        "trust_tier": "A",
        "fetch_status": "pdf_ok",
        "page_spans": page_spans,
    }

    extracted = evidence.extract_evidence_for_claim(
        "世界卫生组织在2023年宣布阿斯巴甜被列为IARC 1类确定致癌物。",
        source,
        text,
    )

    assert extracted
    assert extracted[0]["page_offsets"]["page_start"] == 2
    assert extracted[0]["page_offsets"]["page_end"] == 2


def test_pdf_text_with_spans_preserves_page_boundaries():
    text, page_spans = fetching._pdf_text_with_spans([" first page ", "second\npage"])

    assert text == "first page second page"
    assert page_spans == [
        {"page": 1, "start": 0, "end": 10},
        {"page": 2, "start": 11, "end": 22},
    ]


def test_numeric_evidence_does_not_compare_protein_count_with_molecular_weight():
    constraints = numeric_evidence.extract_numeric_constraints("鸡蛋中含有超过1500种独特蛋白质")
    passage_mentions = numeric_evidence.extract_numeric_mentions(
        "A 7 kDa protein was identified and a sequence covered 42% of the entire protein."
    )

    assert constraints
    assert passage_mentions
    assert not any(
        numeric_evidence.numeric_context_related(constraints[0], mention)
        and numeric_evidence.numeric_conflicts(constraints[0], mention)
        for mention in passage_mentions
    )


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


def test_verdict_summary_counts_mixed_geo_conflicts():
    summary = verdict.summarize_claims(
        {
            "claims": [
                {"online": {"checked": True, "status": "supported", "verdict": "找到权威相关资料"}},
                {"online": {"checked": True, "status": "mixed", "verdict": "证据混合"}},
                {"online": {"checked": True, "status": "refuted", "verdict": "证据反驳"}},
            ],
            "overall": {"score": 50},
        },
        checked=3,
    )

    assert summary["supported_count"] == 1
    assert summary["refuted_count"] == 1
    assert summary["mixed_count"] == 1
    assert "混合/冲突证据" in summary["summary"]


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


def test_source_registry_marks_known_authority_as_tier_a():
    source = source_intel.classify_source(
        {"url": "https://www.who.int/news/item/aspartame", "title": "WHO release"},
        {
            "url": "https://www.who.int/news/item/aspartame",
            "canonical_url": "https://www.who.int/news/item/aspartame",
            "title": "WHO release",
            "fetch_status": "ok",
            "text": "World Health Organization body text.",
        },
    )

    assert source["trust_tier"] == "A"
    assert any("source registry matched who.int" in reason for reason in source["trust_reasons"])


def test_source_id_is_stable_for_same_canonical_and_content():
    first = source_intel.classify_source(
        {"url": "https://www.who.int/news/item/aspartame?utm=1", "title": "WHO release"},
        {
            "url": "https://www.who.int/news/item/aspartame?utm=1",
            "canonical_url": "https://www.who.int/news/item/aspartame",
            "title": "WHO release",
            "fetch_status": "ok",
            "text": "same body",
        },
    )
    second = source_intel.classify_source(
        {"url": "https://www.who.int/news/item/aspartame", "title": "WHO release"},
        {
            "url": "https://www.who.int/news/item/aspartame",
            "canonical_url": "https://www.who.int/news/item/aspartame",
            "title": "WHO release",
            "fetch_status": "ok",
            "text": "same body",
        },
    )

    assert first["source_id"].startswith("src-")
    assert first["source_id"] == second["source_id"]


def test_source_registry_loads_external_registry_data():
    data = source_registry.registry_data()

    assert data["authoritative_domains"]["who.int"]["tier"] == "A"
    assert "localhost" in data["blocked_domains"]
    assert data["risky_domains"]["top10-example.com"] == "content_farm"
    assert "who.int" in data["authority_brand_tokens"]["who"]


def test_source_registry_normalizes_url_hosts_and_matches_subdomains():
    domain = source_registry.domain_from_url("https://user:pass@www.cdc.gov:443/report?utm=1")
    metadata = source_registry.lookup_domain("updates.cdc.gov")

    assert domain == "cdc.gov"
    assert metadata["domain"] == "cdc.gov"
    assert metadata["tier"] == "A"


def test_source_intel_flags_fake_authority_domain():
    source = source_intel.classify_source(
        {"url": "https://who-int.example.com/aspartame", "title": "WHO official release"},
        {
            "url": "https://who-int.example.com/aspartame",
            "canonical_url": "https://who-int.example.com/aspartame",
            "title": "WHO official release",
            "publisher": "World Health Organization",
            "fetch_status": "ok",
            "text": "Aspartame is safe.",
        },
    )

    assert source["trust_tier"] == "D"
    assert "fake_authority" in source["risk_flags"]


def test_source_intel_flags_fake_authority_title_impersonation():
    source = source_intel.classify_source(
        {
            "url": "https://health-news-example.com/aspartame",
            "title": "WHO official release on aspartame",
        },
        {
            "url": "https://health-news-example.com/aspartame",
            "canonical_url": "https://health-news-example.com/aspartame",
            "title": "WHO official release on aspartame",
            "fetch_status": "ok",
            "text": "This page claims to be an official WHO release.",
        },
    )

    assert source["trust_tier"] == "D"
    assert "fake_authority" in source["risk_flags"]


def test_source_intel_blocks_local_domains_even_with_ports():
    source = source_intel.classify_source(
        {"url": "http://localhost:8000/internal", "title": "Local"},
        {
            "url": "http://localhost:8000/internal",
            "canonical_url": "http://localhost:8000/internal",
            "title": "Local",
            "fetch_status": "ok",
            "text": "Local body.",
        },
    )

    assert source["trust_tier"] == "blocked"
    assert "blocked_domain" in source["risk_flags"]


def test_source_intel_does_not_flag_news_title_mentions_as_fake_authority():
    source = source_intel.classify_source(
        {"url": "https://www.reuters.com/world/who-report", "title": "WHO releases new report"},
        {
            "url": "https://www.reuters.com/world/who-report",
            "canonical_url": "https://www.reuters.com/world/who-report",
            "title": "WHO releases new report",
            "publisher": "Reuters",
            "fetch_status": "ok",
            "text": "Reuters reported that WHO released a new report.",
        },
    )

    assert source["trust_tier"] == "B"
    assert "fake_authority" not in source["risk_flags"]


def test_source_intel_flags_canonical_anomaly():
    source = source_intel.classify_source(
        {"url": "https://example.com/report", "title": "Report"},
        {
            "url": "https://example.com/report",
            "canonical_url": "https://content-farm.example.net/copy",
            "title": "Report",
            "fetch_status": "ok",
            "text": "Copied body.",
        },
    )

    assert "canonical_anomaly" in source["risk_flags"]


def test_source_intel_flags_redirect_anomaly():
    source = source_intel.classify_source(
        {"url": "https://official.example.com/report", "title": "Report"},
        {
            "url": "https://content-farm.example.net/report",
            "canonical_url": "https://content-farm.example.net/report",
            "redirect_chain": [
                "https://official.example.com/report",
                "https://content-farm.example.net/report",
            ],
            "title": "Report",
            "fetch_status": "ok",
            "text": "Redirected body.",
        },
    )

    assert "redirect_anomaly" in source["risk_flags"]
    assert source["redirect_chain"][-1] == "https://content-farm.example.net/report"


def test_source_intel_flags_missing_source_identity():
    source = source_intel.classify_source(
        {"url": "https://unknown-example.com/report", "title": "Report"},
        {
            "url": "https://unknown-example.com/report",
            "canonical_url": "https://unknown-example.com/report",
            "title": "Report",
            "fetch_status": "ok",
            "text": "A report body without publisher, author, or date.",
        },
    )

    assert "missing_source_identity" in source["risk_flags"]
    assert "missing_publisher" in source["risk_flags"]
    assert "missing_author" in source["risk_flags"]
    assert "missing_published_date" in source["risk_flags"]


def test_source_intel_flags_partial_identity_gaps_without_full_identity_failure():
    source = source_intel.classify_source(
        {"url": "https://example-news.com/report", "title": "Report"},
        {
            "url": "https://example-news.com/report",
            "canonical_url": "https://example-news.com/report",
            "title": "Report",
            "publisher": "Example News",
            "fetch_status": "ok",
            "text": "A report body with publisher but no byline or date.",
        },
    )

    assert "missing_source_identity" not in source["risk_flags"]
    assert "missing_publisher" not in source["risk_flags"]
    assert "missing_author" in source["risk_flags"]
    assert "missing_published_date" in source["risk_flags"]


def test_source_intel_annotates_reposted_low_tier_content():
    sources = [
        {
            "url": "https://blog-a.example/post",
            "domain": "blog-a.example",
            "trust_tier": "D",
            "content_hash": "same",
            "risk_flags": [],
        },
        {
            "url": "https://blog-b.example/post",
            "domain": "blog-b.example",
            "trust_tier": "D",
            "content_hash": "same",
            "risk_flags": [],
        },
    ]

    annotated = source_intel.annotate_cross_source_risks(sources)

    assert all("press_release_repost" in source["risk_flags"] for source in annotated)


def test_source_intel_annotates_content_farm_cluster():
    sources = [
        {
            "url": "https://top10-example.com/a",
            "domain": "top10-example.com",
            "trust_tier": "D",
            "content_hash": "a",
            "risk_flags": ["content_farm", "biased_listicle"],
        },
        {
            "url": "https://rank-example.com/b",
            "domain": "rank-example.com",
            "trust_tier": "D",
            "content_hash": "b",
            "risk_flags": ["content_farm", "biased_listicle"],
        },
    ]

    annotated = source_intel.annotate_cross_source_risks(sources)

    assert all("content_farm_cluster" in source["risk_flags"] for source in annotated)


def test_fetching_records_redirect_chain():
    class Response:
        url = "https://example.com/final"
        headers = {"content-type": "text/html"}
        content = b"<html><head><title>Final</title></head><body>Final body text.</body></html>"
        encoding = "utf-8"

        class HistoryItem:
            url = "https://example.com/start"

        history = [HistoryItem()]

        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _url):
            return Response()

    snapshot = fetching.fetch_source_snapshot("https://example.com/start", client_factory=Client)

    assert snapshot["fetch_status"] == "ok"
    assert snapshot["redirect_chain"] == ["https://example.com/start", "https://example.com/final"]


def test_fetching_extracts_schema_org_identity_metadata():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "NewsArticle",
          "headline": "Structured headline",
          "datePublished": "2026-06-20T10:00:00Z",
          "author": {"@type": "Person", "name": "Jane Reporter"},
          "publisher": {"@type": "Organization", "name": "Example News"}
        }
        </script>
      </head>
      <body>Structured body text.</body>
    </html>
    """

    snapshot = fetching._html_snapshot("https://example-news.com/story", html)
    source = source_intel.classify_source({"url": snapshot["url"]}, snapshot)

    assert snapshot["title"] == "Structured headline"
    assert snapshot["publisher"] == "Example News"
    assert snapshot["author"] == "Jane Reporter"
    assert snapshot["published_at"] == "2026-06-20T10:00:00Z"
    assert "missing_source_identity" not in source["risk_flags"]


def test_fetching_resolves_schema_org_graph_identity_references():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "NewsArticle",
              "headline": "Graph headline",
              "datePublished": "2026-06-21",
              "publisher": {"@id": "#publisher"},
              "author": {"@id": "#author"}
            },
            {
              "@id": "#publisher",
              "@type": "Organization",
              "name": "Graph News"
            },
            {
              "@id": "#author",
              "@type": "Person",
              "name": "Alex Reporter"
            }
          ]
        }
        </script>
      </head>
      <body>Graph body text.</body>
    </html>
    """

    snapshot = fetching._html_snapshot("https://graph-news.example/story", html)
    source = source_intel.classify_source({"url": snapshot["url"]}, snapshot)

    assert snapshot["title"] == "Graph headline"
    assert snapshot["publisher"] == "Graph News"
    assert snapshot["author"] == "Alex Reporter"
    assert snapshot["published_at"] == "2026-06-21"
    assert "missing_source_identity" not in source["risk_flags"]


def test_fetching_reads_time_datetime_and_dc_metadata():
    html = """
    <html>
      <head>
        <title>Fallback title</title>
        <meta name="dc.creator" content="Research Team" />
        <meta name="dc.publisher" content="Example Institute" />
      </head>
      <body>
        <time datetime="2026-06-19">June 19, 2026</time>
        Fallback body text.
      </body>
    </html>
    """

    snapshot = fetching._html_snapshot("https://example.edu/report", html)

    assert snapshot["publisher"] == "Example Institute"
    assert snapshot["author"] == "Research Team"
    assert snapshot["published_at"] == "2026-06-19"
