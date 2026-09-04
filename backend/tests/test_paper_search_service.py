import pathlib
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from app.services.academic_evidence import (
    ai_venue_ids,
    allowed_venue_catalog,
    match_allowed_venue,
    security_venue_ids,
    systems_venue_ids,
)
from app.services.paper_search_service import (
    CrossrefAdapter,
    GoogleScholarAdapter,
    ElasticsearchIndex,
    InvertedIndex,
    OpenAlexAdapter,
    PaperSearchService,
    SemanticScholarAdapter,
    _arxiv_query,
    _parse_arxiv_feed,
    extract_keywords,
    public_academic_client_kwargs,
)


ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2601.00001v1</id>
    <title>Adaptive Prompt Injection Against LLM Safety Filters</title>
    <summary>We study prompt injection attacks that adaptively evade safety filters.</summary>
    <author><name>Alice Chen</name></author>
    <category term="cs.CR"/>
    <arxiv:comment>To appear in USENIX Security 2026</arxiv:comment>
    <published>2026-01-03T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.00002v1</id>
    <title>Prompt Injection Benchmarks for Agents</title>
    <summary>A broad benchmark of prompt injection attacks with no venue information.</summary>
    <author><name>Bob Liu</name></author>
    <category term="cs.AI"/>
    <published>2026-01-04T00:00:00Z</published>
  </entry>
</feed>"""


class FakeResponse:
    def __init__(self, *, text=ARXIV_FEED, payload=None, status_code=200):
        self.text = text
        self._payload = payload or {}
        self.status_code = status_code
        self.content = text.encode("utf-8") if text else b"{}"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._payload


class FakeArxivClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        assert "export.arxiv.org" in url
        return FakeResponse()


def make_service(tmp_path: pathlib.Path, **kwargs):
    return PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "paper-index.json"),
        client_factory=FakeArxivClient,
        require_proxy=False,
        **kwargs,
    )


def test_core_catalog_contains_security_systems_and_requested_ai_venues():
    assert set(security_venue_ids()) == {"ieee_sp", "usenix_security", "acm_ccs", "ndss"}
    assert {"usenix_osdi", "acm_sosp", "asplos", "eurosys", "usenix_atc", "sigcomm", "nsdi", "fast"}.issubset(systems_venue_ids())
    assert set(ai_venue_ids()) == {"iclr", "icml", "aaai", "neurips", "acl"}
    assert {meta["track"] for meta in allowed_venue_catalog().values()} == {"security", "systems", "ai"}


def test_neurips_accepts_current_and_legacy_nips_name():
    assert match_allowed_venue("NeurIPS 2026")["id"] == "neurips"
    assert match_allowed_venue("Advances in Neural Information Processing Systems (NIPS 2016)")["id"] == "neurips"


def test_arxiv_parser_canonicalizes_pdf_and_keeps_metadata_boundary():
    papers = _parse_arxiv_feed(ARXIV_FEED)
    assert len(papers) == 2
    assert papers[0]["source_url"].startswith("https://arxiv.org/abs/")
    assert papers[0]["pdf_url"].startswith("https://arxiv.org/pdf/")
    assert papers[0]["pdf_url"].endswith(".pdf")


def test_layered_search_returns_core_before_arxiv_and_discloses_freshness(tmp_path):
    result = make_service(tmp_path).search(
        query="prompt injection agents",
        tracks=("security", "ai"),
        include_arxiv=True,
        include_scholar=True,
        include_crossref=False,
        include_openalex=False,
        limit=10,
    )

    assert [paper["scope_tier"] for paper in result["results"]] == ["core", "arxiv"]
    assert all(paper["evidence_status"] == "discovery_metadata" for paper in result["results"])
    assert all(paper["full_text_verified"] is False for paper in result["results"])
    assert result["scope_counts"] == {"core": 1, "arxiv": 1, "scholar": 0}
    assert result["provider_status"]["google_scholar"]["reason"] == "not_configured"
    assert result["index_updated_at"]
    assert result["retrieved_at"]
    assert result["search_backend"] == "local_inverted_index"
    assert result["elasticsearch_available"] is False
    assert "Google Scholar" in result["coverage_note"]


def test_index_persists_and_supports_refresh_false(tmp_path):
    cache = tmp_path / "paper-index.json"
    first = PaperSearchService(
        index=InvertedIndex(cache_path=cache),
        client_factory=FakeArxivClient,
        require_proxy=False,
    )
    first.search(
        query="prompt injection",
        include_arxiv=True,
        include_scholar=False,
        include_crossref=False,
        include_openalex=False,
    )
    second = PaperSearchService(
        index=InvertedIndex(cache_path=cache),
        client_factory=FakeArxivClient,
        require_proxy=False,
    )
    result = second.search(
        query="prompt injection",
        refresh=False,
        include_arxiv=True,
        include_scholar=False,
        include_crossref=False,
        include_openalex=False,
    )
    assert result["fetched_this_run"] == 0
    assert result["result_count"] == 2
    assert result["index_stats"]["documents"] == 2


def test_single_term_query_can_return_title_keyword_matches(tmp_path):
    result = make_service(tmp_path).search(
        query="LLM",
        tracks=("security", "ai"),
        include_arxiv=True,
        include_scholar=False,
        include_crossref=False,
        include_openalex=False,
    )

    assert result["result_count"] == 1
    assert result["results"][0]["title"] == "Adaptive Prompt Injection Against LLM Safety Filters"


def test_venue_filter_keeps_unconfirmed_external_results_when_requested(tmp_path):
    result = make_service(tmp_path).search(
        query="prompt injection",
        tracks=("security", "ai"),
        venue_ids=("iclr",),
        include_unconfirmed=True,
        include_arxiv=True,
        include_scholar=False,
        include_crossref=False,
        include_openalex=False,
    )

    assert [paper["title"] for paper in result["results"]] == ["Prompt Injection Benchmarks for Agents"]
    assert result["scope_counts"] == {"core": 0, "arxiv": 1, "scholar": 0}


class FakeScholarClient:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        return FakeResponse(
            text="",
            payload={
                "organic_results": [
                    {
                        "title": "A Classic Study of Prompt Injection",
                        "link": "https://dl.acm.org/doi/10.1145/1234567.1234568",
                        "snippet": "A classic paper about prompt injection.",
                        "publication_info": {"summary": "Alice Example - ACM CCS, 2024"},
                        "inline_links": {"cited_by": {"total": 42}},
                    }
                ]
            },
        )


def test_google_scholar_adapter_reports_configured_metadata_results():
    adapter = GoogleScholarAdapter(
        endpoint="https://scholar-api.example/search",
        client_factory=FakeScholarClient,
        require_proxy=False,
    )
    papers, status = adapter.search("prompt injection", 5)
    assert status["available"] is True
    assert papers[0]["source"] == "google_scholar"
    assert papers[0]["cited_by"] == 42
    assert papers[0]["doi"] == "10.1145/1234567.1234568"


class FakeOpenMetadataClient:
    seen_queries = []
    seen_requests = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        params = kwargs.get("params") or {}
        self.__class__.seen_requests.append((url, params))
        self.__class__.seen_queries.append(
            (url, params.get("search") or params.get("query") or params.get("query.bibliographic"))
        )
        if "crossref.org" in url:
            return FakeResponse(
                text="",
                payload={
                    "message": {
                        "items": [
                            {
                                "DOI": "10.5555/crossref.values",
                                "title": ["Value Alignment Benchmarks Need Grounded Evaluation"],
                                "abstract": "<jats:p>A grounded benchmark for language model value alignment.</jats:p>",
                                "author": [
                                    {"given": "Casey", "family": "Researcher"},
                                    {"given": "Lin", "family": "Example"},
                                ],
                                "container-title": ["Journal of AI Evaluation"],
                                "published-online": {"date-parts": [[2025, 4, 3]]},
                                "URL": "https://doi.org/10.5555/crossref.values",
                                "type": "journal-article",
                                "is-referenced-by-count": 23,
                                "subject": ["Artificial Intelligence"],
                            }
                        ]
                    }
                },
            )
        if "openalex.org" in url:
            return FakeResponse(
                text="",
                payload={
                    "results": [
                        {
                            "id": "https://openalex.org/W4400000001",
                            "doi": "https://doi.org/10.5555/eigen.neighbor",
                            "display_name": "Value Alignment Benchmarks Need Grounded Leaderboards",
                            "publication_year": 2025,
                            "publication_date": "2025-05-10",
                            "authorships": [
                                {"author": {"display_name": "Ada Example"}},
                                {"author": {"display_name": "Lin Researcher"}},
                            ],
                            "primary_location": {
                                "landing_page_url": "https://publisher.example/eigen-neighbor",
                                "source": {"display_name": "International Conference on Learning Representations"},
                            },
                            "best_oa_location": {"pdf_url": "https://archive.example/eigen-neighbor.pdf"},
                            "abstract_inverted_index": {
                                "Value": [0],
                                "alignment": [1],
                                "benchmarks": [2],
                                "need": [3],
                                "grounded": [4],
                                "leaderboards": [5],
                            },
                            "cited_by_count": 17,
                            "type": "article",
                            "topics": [{"display_name": "AI Evaluation"}],
                        }
                    ]
                },
            )
        if "semanticscholar.org" in url:
            return FakeResponse(
                text="",
                payload={
                    "data": [
                        {
                            "paperId": "s2-eigen-neighbor",
                            "title": "Pluralistic Value Evaluation for Language Models",
                            "abstract": "A benchmark for pluralistic value evaluation and alignment.",
                            "year": 2024,
                            "authors": [{"name": "Sam Example"}],
                            "venue": "NeurIPS",
                            "externalIds": {"DOI": "10.5555/plural.values"},
                            "url": "https://www.semanticscholar.org/paper/s2-eigen-neighbor",
                            "openAccessPdf": {"url": "https://archive.example/plural-values.pdf"},
                            "citationCount": 9,
                            "publicationDate": "2024-12-01",
                        }
                    ]
                },
            )
        raise AssertionError(url)


def test_openalex_no_key_adapter_keeps_complete_bibliography_and_real_links():
    FakeOpenMetadataClient.seen_queries = []
    adapter = OpenAlexAdapter(client_factory=FakeOpenMetadataClient, require_proxy=False)

    papers, status = adapter.search(
        ["EigenBench value alignment", "grounded leaderboard", "ignored fourth", "not reached"],
        12,
    )

    assert status == {
        "configured": True,
        "available": True,
        "provider": "openalex_public_api",
        "result_count": 1,
        "query_count": 3,
    }
    assert len(FakeOpenMetadataClient.seen_queries) == 3
    assert papers[0]["authors"] == ["Ada Example", "Lin Researcher"]
    assert papers[0]["year"] == 2025
    assert papers[0]["doi"] == "10.5555/eigen.neighbor"
    assert papers[0]["source_url"] == "https://doi.org/10.5555/eigen.neighbor"
    assert papers[0]["metadata_url"] == "https://openalex.org/W4400000001"
    assert papers[0]["pdf_url"].endswith("eigen-neighbor.pdf")
    assert papers[0]["abstract"] == "Value alignment benchmarks need grounded leaderboards"


def test_openalex_arxiv_mode_limits_requests_to_arxiv_source():
    FakeOpenMetadataClient.seen_requests = []
    adapter = OpenAlexAdapter(
        client_factory=FakeOpenMetadataClient,
        require_proxy=False,
        arxiv_only=True,
    )

    _, status = adapter.search(["multilingual retrieval"], 5)

    assert status["available"] is True
    request_params = FakeOpenMetadataClient.seen_requests[-1][1]
    assert request_params["filter"] == "locations.source.id:S4306400194"


def test_crossref_is_primary_no_key_metadata_adapter():
    adapter = CrossrefAdapter(client_factory=FakeOpenMetadataClient, require_proxy=False)

    papers, status = adapter.search(["value alignment grounded benchmark"], 5)

    assert status["provider"] == "crossref_rest_api"
    assert status["available"] is True
    assert papers[0]["source"] == "crossref"
    assert papers[0]["doi"] == "10.5555/crossref.values"
    assert papers[0]["authors"] == ["Casey Researcher", "Lin Example"]
    assert papers[0]["published_at"] == "2025-04-03"
    assert papers[0]["abstract"] == "A grounded benchmark for language model value alignment."


def test_crossref_accepts_partial_date_parts_with_null_month_and_day():
    paper = CrossrefAdapter._normalize(
        {
            "DOI": "10.5555/partial.date",
            "title": ["A Paper with a Year-Only Date"],
            "published": {"date-parts": [[2026, None, None]]},
        }
    )

    assert paper is not None
    assert paper["year"] == 2026
    assert paper["published_at"] == "2026"


def test_semantic_scholar_no_key_adapter_returns_citable_metadata():
    adapter = SemanticScholarAdapter(client_factory=FakeOpenMetadataClient, require_proxy=False)

    papers, status = adapter.search(["pluralistic value evaluation"], 5)

    assert status["available"] is True
    assert status["provider"] == "semantic_scholar_graph_api"
    assert papers[0]["authors"] == ["Sam Example"]
    assert papers[0]["journal_ref"] == "NeurIPS"
    assert papers[0]["source_url"] == "https://doi.org/10.5555/plural.values"
    assert papers[0]["metadata_url"].startswith("https://www.semanticscholar.org/paper/")


def test_open_metadata_providers_fail_closed_without_required_proxy():
    openalex = OpenAlexAdapter(proxy_url="", require_proxy=True)
    semantic = SemanticScholarAdapter(proxy_url="", require_proxy=True)

    _, openalex_status = openalex.search(["value alignment"], 5)
    _, semantic_status = semantic.search(["value alignment"], 5)

    assert openalex_status["reason"] == "proxy_required"
    assert semantic_status["reason"] == "proxy_required"


def test_layered_search_runs_open_metadata_in_parallel_and_preserves_source_links(tmp_path):
    service = PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "paper-index.json"),
        client_factory=FakeOpenMetadataClient,
        require_proxy=False,
    )

    result = service.search(
        query="value alignment benchmark grounded leaderboard",
        semantic_queries=(
            "EigenBench value alignment",
            "grounded leaderboard",
            "pluralistic evaluation",
            "must be ignored",
        ),
        include_arxiv=False,
        include_scholar=False,
        include_semantic_scholar=True,
        limit=10,
    )

    assert result["semantic_queries"] == [
        "EigenBench value alignment",
        "grounded leaderboard",
        "pluralistic evaluation",
    ]
    assert result["provider_status"]["openalex"]["available"] is True
    assert result["provider_status"]["crossref"]["available"] is True
    assert result["provider_status"]["semantic_scholar"]["available"] is True
    assert {paper["source"] for paper in result["results"]} == {
        "openalex",
        "crossref",
        "semantic_scholar",
    }
    assert all(paper["source_url"].startswith("https://") for paper in result["results"])
    assert all(paper["source_links"] for paper in result["results"])
    assert all(paper["evidence_status"] == "discovery_metadata" for paper in result["results"])


class ResolvedCitationOpenAlex:
    configured = True

    def search(self, queries, limit):
        assert queries[2] == "LitmusValues"
        return [
            {
                "id": "openalex-W4415024593",
                "title": "Will AI Tell Lies to Save Sick Children? Litmus-Testing AI Values Prioritization",
                "abstract": "Language model values and alignment benchmark.",
                "authors": ["Yu Ying Chiu", "Zhilin Wang"],
                "categories": [],
                "journal_ref": "arXiv",
                "doi": "10.48550/arxiv.2505.14633",
                "year": 2025,
                "source_url": "https://doi.org/10.48550/arxiv.2505.14633",
                "pdf_url": "https://arxiv.org/pdf/2505.14633",
                "metadata_url": "https://openalex.org/W4415024593",
                "source": "openalex",
                "provider_query_indexes": [2],
                "provider_query_hits": 1,
                "provider_query_ranks": {"2": 1},
            }
        ], {"configured": True, "available": True, "result_count": 1, "query_count": 3}


def test_page_citation_alias_is_resolved_to_public_metadata_without_duplicate(tmp_path):
    service = PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "paper-index.json"),
        openalex=ResolvedCitationOpenAlex(),
        require_proxy=False,
    )
    result = service.search(
        query="eigenbench value alignment LitmusValues",
        semantic_queries=("eigenbench value alignment", "ground truth alignment", "LitmusValues"),
        include_arxiv=False,
        include_scholar=False,
        include_crossref=False,
        include_semantic_scholar=False,
        local_candidates=[
            {
                "id": "bibliography-litmus",
                "title": "LitmusValues",
                "abstract": "Which values are prioritized by a language model?",
                "authors": ["Chiu"],
                "year": 2025,
                "source": "paper_bibliography",
                "provenance": {
                    "provider": "paper_bibliography",
                    "source_page": 4,
                    "exact_quote": "LitmusValues (Chiu et al., 2025)",
                    "metadata_only": True,
                },
            }
        ],
    )

    assert [paper["source"] for paper in result["results"]] == ["openalex"]
    resolved = result["results"][0]
    assert resolved["doi"] == "10.48550/arxiv.2505.14633"
    assert resolved["provenance"]["source_page"] == 4
    assert resolved["provenance"]["exact_quote"] == "LitmusValues (Chiu et al., 2025)"
    assert resolved["discovery_sources"] == ["openalex", "paper_bibliography"]


def test_public_academic_client_proxy_is_explicit_and_ignores_process_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://process-wide-proxy.invalid:9000")
    monkeypatch.setenv("PAPER_SEARCH_PROXY_URL", "http://127.0.0.1:7897")

    kwargs = public_academic_client_kwargs()

    assert kwargs["proxy"] == "http://127.0.0.1:7897"
    assert kwargs["trust_env"] is False


def test_public_academic_provider_fails_closed_when_proxy_is_required(tmp_path):
    service = PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "paper-index.json"),
        client_factory=FakeArxivClient,
        proxy_url="",
        require_proxy=True,
    )

    result = service.search(
        query="prompt injection",
        include_arxiv=True,
        include_scholar=False,
        include_crossref=False,
        include_openalex=False,
    )

    assert result["provider_status"]["arxiv"] == {
        "configured": True,
        "available": False,
        "reason": "proxy_required",
        "via_proxy": False,
    }
    assert result["network_policy"]["public_direct_allowed"] is False


class RecordingAcademicClient(FakeArxivClient):
    seen_kwargs = []

    def __init__(self, **kwargs):
        self.__class__.seen_kwargs.append(kwargs)
        super().__init__(**kwargs)


def test_arxiv_client_receives_only_configured_academic_proxy(tmp_path):
    RecordingAcademicClient.seen_kwargs = []
    service = PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "paper-index.json"),
        client_factory=RecordingAcademicClient,
        proxy_url="http://127.0.0.1:7897",
        require_proxy=True,
    )

    result = service.search(
        query="prompt injection",
        include_arxiv=True,
        include_scholar=False,
        include_crossref=False,
        include_openalex=False,
    )

    assert result["provider_status"]["arxiv"]["available"] is True
    assert result["provider_status"]["arxiv"]["via_proxy"] is True
    assert result["network_policy"] == {
        "academic_proxy_required": True,
        "academic_proxy_configured": True,
        "public_direct_allowed": False,
        "elasticsearch_uses_academic_proxy": False,
    }
    assert RecordingAcademicClient.seen_kwargs[0]["proxy"] == "http://127.0.0.1:7897"
    assert RecordingAcademicClient.seen_kwargs[0]["trust_env"] is False


def test_elasticsearch_client_stays_direct_when_academic_proxy_is_configured(monkeypatch):
    monkeypatch.setenv("PAPER_SEARCH_PROXY_URL", "http://127.0.0.1:7897")

    kwargs = ElasticsearchIndex(url="http://127.0.0.1:9200")._client_kwargs()

    assert "proxy" not in kwargs
    assert kwargs["trust_env"] is False


def test_elasticsearch_mapping_defaults_to_single_node_and_allows_replica_override(monkeypatch):
    monkeypatch.delenv("PAPER_SEARCH_ES_REPLICAS", raising=False)
    index = ElasticsearchIndex(url="http://127.0.0.1:9200")

    assert index._mapping()["settings"] == {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    }

    monkeypatch.setenv("PAPER_SEARCH_ES_REPLICAS", "2")
    assert index._mapping()["settings"]["number_of_replicas"] == 2


class DynamicConfigElasticsearch:
    url = ""

    def health(self):
        return {"configured": bool(self.url), "available": False, "error": "offline"}


def test_saved_search_connections_apply_on_next_search_without_restart(tmp_path):
    configs = iter(
        [
            SimpleNamespace(
                paper_search_proxy_url="http://127.0.0.1:7001",
                google_scholar_api_url="https://scholar-one.example/search",
                serpapi_api_key="first-key",
                elasticsearch_url="http://127.0.0.1:9201",
            ),
            SimpleNamespace(
                paper_search_proxy_url="http://127.0.0.1:7002",
                google_scholar_api_url="https://scholar-two.example/search",
                serpapi_api_key="second-key",
                elasticsearch_url="http://127.0.0.1:9202",
            ),
        ]
    )
    elasticsearch = DynamicConfigElasticsearch()
    service = PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "paper-index.json"),
        elasticsearch=elasticsearch,
        require_proxy=True,
        connection_config_factory=lambda: next(configs),
    )

    service.search(
        query="value alignment",
        refresh=False,
        include_arxiv=False,
        include_scholar=False,
    )
    assert service.proxy_url == "http://127.0.0.1:7001"
    assert service.openalex.proxy_url == service.proxy_url
    assert service.semantic_scholar.proxy_url == service.proxy_url
    assert service.scholar.endpoint == "https://scholar-one.example/search"
    assert service.scholar.api_key == "first-key"
    assert elasticsearch.url == "http://127.0.0.1:9201"

    service.search(
        query="value alignment",
        refresh=False,
        include_arxiv=False,
        include_scholar=False,
    )
    assert service.proxy_url == "http://127.0.0.1:7002"
    assert service.openalex.proxy_url == service.proxy_url
    assert service.semantic_scholar.proxy_url == service.proxy_url
    assert service.scholar.endpoint == "https://scholar-two.example/search"
    assert service.scholar.api_key == "second-key"
    assert elasticsearch.url == "http://127.0.0.1:9202"


class FailingElasticsearch:
    def health(self):
        return {"configured": True, "available": True, "status": "green"}

    def index_many(self, papers):
        raise RuntimeError("bulk unavailable")

    def search(self, query, *, limit):
        raise AssertionError("search must not run after indexing failure")


class EmptyHealthyElasticsearch:
    def health(self):
        return {"configured": True, "available": True, "status": "green"}

    def index_many(self, papers):
        return len(papers)

    def search(self, query, *, limit):
        return []


def test_active_elasticsearch_keeps_request_local_bibliography_candidates(tmp_path):
    result = make_service(tmp_path, elasticsearch=EmptyHealthyElasticsearch()).search(
        query="efficient model evaluation",
        refresh=False,
        include_arxiv=False,
        include_scholar=False,
        local_candidates=[
            {
                "id": "bibliography-efficient-evaluation",
                "title": "Efficient model evaluation",
                "abstract": "A source-grounded bibliography lead.",
                "authors": ["Ada Lovelace"],
                "year": 2024,
                "source": "paper_bibliography",
                "provenance": {"provider": "paper_bibliography", "source_page": 8},
            }
        ],
    )

    assert result["search_backend"] == "elasticsearch"
    assert [paper["title"] for paper in result["results"]] == ["Efficient model evaluation"]
    assert result["results"][0]["scope_tier"] == "local"


def test_elasticsearch_failure_falls_back_to_local_index(tmp_path):
    result = make_service(tmp_path, elasticsearch=FailingElasticsearch()).search(
        query="prompt injection",
        include_arxiv=True,
        include_scholar=False,
        include_crossref=False,
        include_openalex=False,
    )
    assert result["search_backend"] == "local_inverted_index"
    assert result["elasticsearch_available"] is True
    assert "bulk unavailable" in result["search_backend_error"]
    assert result["result_count"] == 2


def test_keyword_fallback_is_deterministic():
    keywords = extract_keywords(
        "Adaptive Prompt Injection Against Safety Filters",
        "We study prompt injection attacks that evade safety filters.",
    )
    assert "prompt" in keywords
    assert "injection" in keywords
    assert "the" not in keywords


def test_arxiv_query_requires_primary_term_and_uses_remaining_terms_for_recall():
    url = _arxiv_query("value alignment ground truth", ("ai",), 20)
    search_query = parse_qs(urlparse(url).query)["search_query"][0]

    assert "all:value" in search_query
    assert {"all:alignment", "all:ground", "all:truth"}.issubset(
        set(re.findall(r"all:[\w-]+", search_query))
    )
    assert "all:value AND all:alignment" not in search_query


def test_local_bibliography_candidates_are_searchable_without_external_refresh(tmp_path):
    service = make_service(tmp_path)
    result = service.search(
        query="value alignment leaderboard",
        refresh=False,
        include_arxiv=False,
        include_scholar=False,
        local_candidates=[
            {
                "id": "bibliography-litmus",
                "title": "LitmusValues",
                "abstract": "Which values are prioritized by a language model alignment benchmark?",
                "authors": ["Chiu"],
                "year": 2025,
                "source": "paper_bibliography",
                "provenance": {
                    "provider": "paper_bibliography",
                    "metadata_only": True,
                    "source_page": 4,
                    "exact_quote": "LitmusValues (Chiu et al., 2025)",
                },
            }
        ],
    )

    assert [paper["title"] for paper in result["results"]] == ["LitmusValues"]
    assert result["results"][0]["scope_tier"] == "local"
    assert result["results"][0]["provenance"]["source_page"] == 4
    assert result["provider_status"]["paper_bibliography"]["available"] is True


def test_general_search_requires_multi_term_metadata_coverage(tmp_path):
    index = InvertedIndex(cache_path=tmp_path / "paper-index.json")
    index.index_many(
        [
            {
                "id": "relevant",
                "title": "Large Language Model Alignment Survey",
                "abstract": "A benchmark of human values and model alignment.",
                "keywords": ["language model", "alignment", "benchmark"],
                "source": "openalex",
                "scope_tier": "scholar",
                "venue": {},
                "track": "ai",
            },
            {
                "id": "genomics",
                "title": "Fast Genome Alignment",
                "abstract": "A benchmark for nucleotide sequence processing.",
                "keywords": ["genome", "alignment"],
                "source": "openalex",
                "scope_tier": "scholar",
                "venue": {},
                "track": "",
            },
        ]
    )
    service = PaperSearchService(index=index, require_proxy=False)

    result = service.search(
        query="language model value alignment benchmark",
        refresh=False,
        include_arxiv=False,
        include_scholar=False,
        include_openalex=True,
        include_semantic_scholar=False,
    )

    assert [paper["id"] for paper in result["results"]] == ["relevant"]
    assert result["search_backend"] == "local_inverted_index"
