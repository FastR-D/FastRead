"""Tests for venue-filtered paper search (security big-four + systems allowlist)."""

import pathlib

import pytest

from app.services.academic_evidence import (
    allowed_venue_catalog,
    match_allowed_venue,
    security_venue_ids,
    systems_venue_ids,
)
from app.services.paper_search_service import (
    InvertedIndex,
    PaperSearchService,
    _parse_arxiv_feed,
    extract_keywords,
)


ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2601.00001v1</id>
    <title>Adaptive Prompt Injection Against LLM Safety Filters</title>
    <summary>We study prompt injection attacks that adaptively evade safety filters.</summary>
    <author><name>Alice Chen</name></author>
    <author><name>Bob Liu</name></author>
    <category term="cs.CR"/>
    <arxiv:comment>To appear in USENIX Security 2026</arxiv:comment>
    <published>2026-01-03T00:00:00Z</published>
    <link title="pdf" href="http://arxiv.org/pdf/2601.00001v1" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.00002v1</id>
    <title>Scalable Kernel Isolation for Multi-Tenant Cloud Systems</title>
    <summary>We present a kernel isolation mechanism for multi-tenant cloud systems.</summary>
    <author><name>Carol Wu</name></author>
    <category term="cs.OS"/>
    <arxiv:journal_ref>Proceedings of OSDI 2026</arxiv:journal_ref>
    <published>2026-01-04T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2601.00003v1</id>
    <title>An Unvenued Study of Prompt Filters</title>
    <summary>A study of prompt filters with no venue information at all.</summary>
    <author><name>Dave Kim</name></author>
    <category term="cs.CR"/>
    <published>2026-01-05T00:00:00Z</published>
  </entry>
</feed>"""


class _FakeResponse:
    status_code = 200
    text = ARXIV_FEED


class _FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        _FakeClient.last_url = url
        return _FakeResponse()


@pytest.fixture()
def service(tmp_path: pathlib.Path) -> PaperSearchService:
    return PaperSearchService(
        index=InvertedIndex(cache_path=tmp_path / "index.json"),
        client_factory=_FakeClient,
    )


# -- venue allowlist --------------------------------------------------------


def test_security_big_four_present():
    assert set(security_venue_ids()) == {"ieee_sp", "usenix_security", "acm_ccs", "ndss"}


def test_systems_allowlist_includes_top_conferences():
    ids = set(systems_venue_ids())
    for expected in ("usenix_osdi", "acm_sosp", "asplos", "eurosys", "usenix_atc", "sigcomm"):
        assert expected in ids


def test_allowed_catalog_tags_tracks():
    catalog = allowed_venue_catalog()
    assert catalog["usenix_security"]["track"] == "security"
    assert catalog["usenix_osdi"]["track"] == "systems"


@pytest.mark.parametrize(
    "text,short_name,track",
    [
        ("Proc. USENIX Security Symposium 2026", "USENIX Security", "security"),
        ("To appear in OSDI 2026", "OSDI", "systems"),
        ("ACM SIGCOMM 2025", "SIGCOMM", "systems"),
        ("NDSS Symposium 2024", "NDSS", "security"),
        ("IEEE Symposium on Security and Privacy", "IEEE S&P", "security"),
    ],
)
def test_match_allowed_venue_hits(text, short_name, track):
    match = match_allowed_venue(text)
    assert match["short_name"] == short_name
    assert match["track"] == track


def test_match_allowed_venue_rejects_unlisted():
    assert match_allowed_venue("Journal of Irrelevant Studies")["id"] == ""
    assert match_allowed_venue("")["id"] == ""


def test_systems_allowlist_configurable(monkeypatch):
    monkeypatch.setenv("PAPER_SEARCH_SYSTEMS_VENUES", "usenix_osdi")
    assert systems_venue_ids() == ("usenix_osdi",)
    catalog = allowed_venue_catalog()
    assert "usenix_osdi" in catalog
    assert "sigcomm" not in catalog


# -- feed parsing & keywords ------------------------------------------------


def test_parse_arxiv_feed_extracts_fields():
    papers = _parse_arxiv_feed(ARXIV_FEED)
    assert len(papers) == 3
    first = papers[0]
    assert first["title"] == "Adaptive Prompt Injection Against LLM Safety Filters"
    assert first["authors"] == ["Alice Chen", "Bob Liu"]
    assert first["comment"] == "To appear in USENIX Security 2026"
    assert first["year"] == 2026
    assert first["pdf_url"].endswith(".pdf") or "pdf" in first["pdf_url"]


def test_parse_arxiv_feed_tolerates_garbage():
    assert _parse_arxiv_feed("not xml at all") == []


def test_extract_keywords_prefers_title_terms():
    keywords = extract_keywords(
        "Adaptive Prompt Injection Against Safety Filters",
        "We study prompt injection attacks that evade safety filters in models.",
    )
    assert "prompt" in keywords
    assert "injection" in keywords
    # stopwords must not leak in
    assert "the" not in keywords and "we" not in keywords


# -- search behaviour -------------------------------------------------------


def test_search_returns_only_venue_confirmed(service):
    out = service.search(query="prompt injection safety filters", limit=10, include_unconfirmed=True)
    assert out["result_count"] == 1
    assert out["results"][0]["venue"]["short_name"] == "USENIX Security"
    # the unvenued paper must be reported separately, never mixed into results
    assert out["venue_unconfirmed_count"] == 1
    assert "Unvenued" in out["venue_unconfirmed"][0]["title"]


def test_search_systems_track(service):
    out = service.search(query="kernel isolation multi-tenant cloud", limit=10)
    titles = [r["title"] for r in out["results"]]
    assert any("Kernel Isolation" in t for t in titles)
    assert out["results"][0]["venue"]["track"] == "systems"


def test_search_track_filter_excludes_other_track(service):
    out = service.search(query="kernel isolation multi-tenant cloud", tracks=("security",), limit=10)
    assert all(r["venue"]["track"] == "security" for r in out["results"])


def test_search_venue_ids_filter(service):
    out = service.search(
        query="prompt injection safety filters",
        venue_ids=("acm_ccs",),
        limit=10,
    )
    assert out["result_count"] == 0  # the USENIX paper is filtered out


def test_search_reports_backend_and_es_absence(service):
    out = service.search(query="prompt injection", limit=5)
    assert out["search_backend"] == "local_inverted_index"
    assert out["elasticsearch_available"] is False
    assert "Elasticsearch" in out["coverage_note"]


def test_search_hides_unconfirmed_by_default(service):
    out = service.search(query="prompt filters", limit=10)
    assert out["venue_unconfirmed"] == []
    assert out["venue_unconfirmed_count"] >= 1


def test_index_persists_across_instances(tmp_path):
    cache = tmp_path / "index.json"
    first = PaperSearchService(index=InvertedIndex(cache_path=cache), client_factory=_FakeClient)
    first.search(query="prompt injection", limit=5)
    # a fresh service with no network refresh still finds the indexed paper
    second = PaperSearchService(index=InvertedIndex(cache_path=cache), client_factory=_FakeClient)
    out = second.search(query="prompt injection", limit=5, refresh=False)
    assert out["fetched_this_run"] == 0
    assert out["result_count"] == 1


def test_index_survives_corrupt_cache(tmp_path):
    cache = tmp_path / "index.json"
    cache.write_text("{not valid json", encoding="utf-8")
    index = InvertedIndex(cache_path=cache)
    assert index.stats() == {"documents": 0, "terms": 0}


def test_search_empty_query_returns_no_results(service):
    out = service.search(query="   ", limit=5)
    assert out["result_count"] == 0
