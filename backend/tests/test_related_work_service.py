from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services import related_work_service
from app.services.related_work_service import RelatedWorkService, _bibliography_candidates


def _paper_result():
    return {
        "paper_task": True,
        "paper_document": {
            "id": "paper-a",
            "title": "Adaptive Prompt Injection",
            "content_hash": "paper-hash",
            "pages": [{"page": 1, "text": "Adaptive prompt injection against agent safety filters."}],
        },
        "insights": {
            "reading_report": {
                "report_version": "report-v2",
                "key_questions": [
                    {
                        "question": "How do adaptive prompt injection attacks evade safety filters?",
                        "answer": "Adaptive attacks compare prompts against agent safety filters.",
                        "evidence": [{"page_start": 1, "page_end": 1}],
                    }
                ],
                "process": [
                    {
                        "step": "Adaptive attack generation",
                        "description": "Generate prompts against agent safety filters.",
                        "evidence": [{"page": 1}],
                    }
                ],
                "contributions": [
                    {
                        "title": "Prompt injection benchmark",
                        "description": "A benchmark for safety filters.",
                        "evidence": [{"page": 1}],
                    }
                ],
            }
        },
    }


class FakeSearch:
    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "results": [
                {
                    "id": "neighbor-low",
                    "title": "Prompt Injection Benchmarks",
                    "authors": ["Bob"],
                    "year": 2024,
                    "venue": {},
                    "keywords": ["prompt injection"],
                    "abstract": "Benchmarking attacks against safety filters.",
                    "source": "arxiv",
                    "source_url": "https://arxiv.org/abs/2401.00001",
                    "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf",
                    "relevance": 2,
                },
                {
                    "id": "neighbor-high",
                    "title": "Adaptive Prompt Injection Against Agent Safety Filters",
                    "authors": ["Alice"],
                    "year": 2026,
                    "venue": {"id": "iclr", "short_name": "ICLR"},
                    "keywords": ["adaptive", "prompt", "injection", "safety", "filters"],
                    "abstract": "Adaptive attacks against agent safety filters.",
                    "source": "core",
                    "source_url": "https://openreview.net/forum?id=neighbor",
                    "relevance": 9,
                },
                # Exact-title self matches are excluded deterministically.
                {"id": "self", "title": "Adaptive Prompt Injection", "year": 2026},
            ],
            "provider_status": {
                "arxiv": {"available": True},
                "google_scholar": {"available": False, "reason": "not_configured"},
            },
            "search_backend": "local_inverted_index",
            "retrieved_at": "2026-08-28T00:00:00+00:00",
        }


def test_related_work_is_metadata_only_ranked_and_bounded(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_result("paper-a", _paper_result())
    search = FakeSearch()
    saved = {}
    monkeypatch.setattr(related_work_service, "get_related_work_by_cache_key", lambda key: saved.get(key))
    monkeypatch.setattr(related_work_service, "save_related_work", lambda snapshot: saved.setdefault(snapshot["cache_key"], snapshot.copy()))

    snapshot = RelatedWorkService(artifacts, search).generate("paper-a", limit=5)

    assert len(snapshot["queries"]) <= 3
    assert search.calls[0]["include_arxiv"] is True
    assert search.calls[0]["include_scholar"] is True
    assert search.calls[0]["prioritize_arxiv"] is True
    assert search.calls[0]["limit"] >= 180
    assert [item["canonical_paper_id"] for item in snapshot["neighbors"]] == [
        "neighbor-high",
        "neighbor-low",
    ]
    assert snapshot["neighbors"][0]["matched_anchor_ids"]
    assert snapshot["neighbors"][0]["overlapping_terms"]
    assert snapshot["neighbors"][0]["abstract"] == "Adaptive attacks against agent safety filters."
    assert "adaptive" in snapshot["neighbors"][0]["keywords"]
    assert snapshot["provider_status"]["google_scholar"]["reason"] == "not_configured"
    assert snapshot["search_backend"] == "local_inverted_index"
    assert snapshot["search_policy"]["mode"] == "keyword_first"
    assert snapshot["search_policy"]["primary_channels"] == ["arxiv", "elasticsearch"]
    assert snapshot["source_counts"] == {"arxiv": 1, "elasticsearch": 1, "supplemental": 0}
    assert snapshot["neighbors"][0]["source_role"] == "primary"
    assert snapshot["neighbors"][0]["discovery_channel"] == "elasticsearch"
    assert snapshot["neighbors"][1]["discovery_channel"] == "arxiv"
    assert snapshot["result_limit"] == 5
    assert "adaptive" in snapshot["search_keywords"]
    assert set(snapshot) == {
        "id",
        "paper_id",
        "paper_content_hash",
        "report_version",
        "cache_key",
        "anchors",
        "queries",
        "search_keywords",
        "search_policy",
        "source_counts",
        "result_limit",
        "neighbors",
        "provider_status",
        "search_backend",
        "generated_at",
        "cache_hit",
    }


def test_related_work_cache_avoids_second_search(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_result("paper-a", _paper_result())
    search = FakeSearch()
    saved = {}
    monkeypatch.setattr(related_work_service, "get_related_work_by_cache_key", lambda key: saved.get(key))

    def save(snapshot):
        saved[snapshot["cache_key"]] = snapshot.copy()
        return snapshot.copy()

    monkeypatch.setattr(related_work_service, "save_related_work", save)
    service = RelatedWorkService(artifacts, search)

    first = service.generate("paper-a")
    second = service.generate("paper-a")

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert len(search.calls) == 1


def test_related_work_rejects_non_paper_artifacts(tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_result("legacy", {"kind": "legacy"})

    try:
        RelatedWorkService(artifacts, FakeSearch()).generate("legacy")
    except ValueError as exc:
        assert "论文任务不存在" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("non-paper artifact must be rejected")


def test_related_work_uses_source_grounded_bibliography_as_local_candidates(monkeypatch, tmp_path):
    result = _paper_result()
    result["paper_document"]["pages"].extend(
        [
            {
                "page": 2,
                "text": (
                    "2 RELATED WORK Prompt Guard (Smith et al., 2024) compares adaptive "
                    "prompt injection defenses. Prompt Guard (Smith et al., 2024) is repeated."
                ),
            },
            {"page": 3, "text": "3 METHODOLOGY We now describe our method."},
        ]
    )
    candidates = _bibliography_candidates(result["paper_document"])

    assert len(candidates) == 1
    assert candidates[0]["title"] == "Prompt Guard"
    assert candidates[0]["year"] == 2024
    assert candidates[0]["provenance"]["provider"] == "paper_bibliography"
    assert candidates[0]["provenance"]["source_page"] == 2
    assert candidates[0]["provenance"]["exact_quote"] == "Prompt Guard (Smith et al., 2024)"

    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_result("paper-a", result)
    search = FakeSearch()
    monkeypatch.setattr(related_work_service, "get_related_work_by_cache_key", lambda _key: None)
    monkeypatch.setattr(related_work_service, "save_related_work", lambda snapshot: snapshot)

    RelatedWorkService(artifacts, search).generate("paper-a", force=True)

    assert search.calls[0]["local_candidates"] == candidates
    assert search.calls[0]["query"].startswith("adaptive prompt injection")


def test_external_neighbor_requires_a_topic_term_in_title_or_keywords():
    anchors, _version = RelatedWorkService._anchors(_paper_result())
    unrelated = {
        "title": "This Ground Truth Is Muddy Anyway",
        "keywords": ["ground truth", "medical datasets"],
        "abstract": "The abstract briefly mentions alignment in medical AI.",
        "source": "openalex",
        "relevance": 10,
        "year": 2025,
    }

    score, matched_ids, overlap = RelatedWorkService._score_neighbor(
        unrelated,
        anchors,
        {"adaptive", "prompt", "injection"},
    )

    assert score == 0
    assert matched_ids == []
    assert overlap == []
