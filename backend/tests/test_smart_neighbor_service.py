import json
from types import SimpleNamespace

from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services import smart_neighbor_service
from app.services.smart_neighbor_service import SmartNeighborService, _normalize_selections


def _snapshot():
    return {
        "id": "snapshot-1",
        "paper_id": "paper-a",
        "paper_content_hash": "paper-hash",
        "report_version": "report-v2",
        "neighbors": [
            {
                "canonical_paper_id": "candidate-a",
                "title": "Adaptive Prompt Injection Benchmarks",
                "abstract": "We compare adaptive attacks against agent safety filters.",
                "keywords": ["prompt injection", "agent safety"],
                "year": 2026,
                "venue": "ICLR",
                "relevance_score": 9.5,
                "discovery_channel": "elasticsearch",
            },
            {
                "canonical_paper_id": "candidate-b",
                "title": "Evaluating Safety Filters",
                "abstract": "A controlled evaluation protocol for safety filters.",
                "keywords": ["evaluation", "safety filters"],
                "year": 2025,
                "venue": "arXiv",
                "relevance_score": 5,
                "discovery_channel": "arxiv",
            },
        ],
    }


def _paper_result():
    return {
        "paper_task": True,
        "paper_document": {
            "title": "Adaptive Prompt Injection",
            "pages": [
                {"page": 1, "text": "Adaptive prompt injection against agent safety filters. " * 100},
                {"page": 2, "text": "We evaluate attacks under controlled threat models. " * 100},
            ],
        },
        "insights": {
            "reading_report": {
                "executive_summary": "The paper studies adaptive prompt injection.",
                "key_questions": [{"question": "What changes under adaptation?", "answer": "Attack success."}],
                "process": [{"step": "Generate", "description": "Generate adaptive attacks."}],
                "contributions": [{"title": "Benchmark", "description": "A controlled benchmark."}],
                "limitations": ["Metadata comparison cannot verify candidate claims."],
            }
        },
    }


def test_smart_selection_start_is_cached_and_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(smart_neighbor_service, "get_latest_related_work", lambda _task_id: _snapshot())
    monkeypatch.setattr(smart_neighbor_service, "get_selection_by_cache_key", lambda _key: None)
    created = {}

    def create(payload):
        created.update(payload)
        return {**payload, "status": "pending", "selections": []}

    monkeypatch.setattr(smart_neighbor_service, "create_selection_job", create)
    service = SmartNeighborService(PaperArtifactRepository(tmp_path))

    job, scheduled = service.start(
        "paper-a",
        provider_id="provider-deepseek",
        model_name="deepseek-v4-flash",
        selection_limit=12,
    )

    assert scheduled is True
    assert job["status"] == "pending"
    assert created["candidate_count"] == 2
    assert created["metadata"]["started_by"] == "explicit_user_smart_selection"
    assert created["metadata"]["evidence_boundary"] == "candidate_metadata_until_full_text_import"
    assert created["metadata"]["selection_limit"] == 12
    assert created["metadata"]["code_filter"] == {
        "minimum_combined_score": 45.0,
        "maximum_background_items": 3,
    }


def test_smart_selection_runs_closed_candidate_model_and_server_scores(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_result("paper-a", _paper_result())
    job = {
        "id": "selection-1",
        "task_id": "paper-a",
        "snapshot_id": "snapshot-1",
        "provider_id": "provider-deepseek",
        "model_name": "deepseek-v4-flash",
        "metadata": {"selection_limit": 12},
    }
    monkeypatch.setattr(smart_neighbor_service, "get_selection_by_id", lambda _selection_id: job)
    monkeypatch.setattr(smart_neighbor_service, "mark_selection_running", lambda _selection_id: job)
    monkeypatch.setattr(smart_neighbor_service, "get_related_work_by_id", lambda _snapshot_id: _snapshot())
    finished = {}

    def finish(selection_id, **kwargs):
        finished.update({"id": selection_id, **kwargs})
        return finished.copy()

    monkeypatch.setattr(smart_neighbor_service, "finish_selection_job", finish)
    captured = {}

    def completion(_client, **kwargs):
        captured.update(kwargs)
        content = json.dumps(
            {
                "selections": [
                    {
                        "candidate_id": "candidate-a",
                        "role": "direct_competitor",
                        "reason": "摘要显示其研究同一类自适应攻击与安全过滤器。",
                        "contrast": "候选全文尚未导入，具体威胁模型仍需核验。",
                        "scores": {
                            "research_problem": 3,
                            "method": 2,
                            "evidence": 2,
                            "novelty_threat": 3,
                        },
                    }
                ]
            },
            ensure_ascii=False,
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    service = SmartNeighborService(
        artifacts,
        model_factory=lambda **_kwargs: SimpleNamespace(client=object(), model="deepseek-v4-flash"),
        completion_factory=completion,
    )
    result = service.run("selection-1")

    assert result["status"] == "completed"
    assert finished["selections"][0]["candidate_id"] == "candidate-a"
    assert finished["selections"][0]["semantic_score"] > 80
    assert finished["metadata"]["validation"] == "candidate_ids_roles_scores_server_verified"
    assert finished["metadata"]["context_policy"]["included_page_count"] == 2
    request_payload = json.loads(captured["messages"][1]["content"])
    assert {item["candidate_id"] for item in request_payload["candidates"]} == {
        "candidate-a",
        "candidate-b",
    }
    assert len(request_payload["source_paper"]["balanced_page_text"]) == 2


def test_smart_selection_rejects_hallucinated_candidate_id():
    payload = {
        "selections": [
            {
                "candidate_id": "invented-paper",
                "role": "background",
                "reason": "This candidate was not in the closed set.",
                "contrast": "",
                "scores": {
                    "research_problem": 1,
                    "method": 1,
                    "evidence": 1,
                    "novelty_threat": 0,
                },
            }
        ]
    }

    try:
        _normalize_selections(payload, _snapshot()["neighbors"], 10)
    except ValueError as exc:
        assert getattr(exc, "reason") == "unknown_candidate_id"
    else:  # pragma: no cover
        raise AssertionError("candidate IDs outside the closed set must be rejected")


def test_smart_selection_code_filter_does_not_fill_with_weak_background_items():
    candidates = [
        {
            "canonical_paper_id": "direct",
            "title": "Direct neighbor",
            "relevance_score": 8,
        },
        *[
            {
                "canonical_paper_id": f"background-{index}",
                "title": f"Background {index}",
                "relevance_score": 5,
            }
            for index in range(5)
        ],
        {
            "canonical_paper_id": "weak",
            "title": "Weak lexical match",
            "relevance_score": 1,
        },
    ]

    def item(candidate_id: str, role: str, score: int):
        return {
            "candidate_id": candidate_id,
            "role": role,
            "reason": "This is a sufficiently detailed model recommendation reason.",
            "contrast": "Candidate full text still needs verification.",
            "scores": {
                "research_problem": score,
                "method": score,
                "evidence": score,
                "novelty_threat": score,
            },
        }

    payload = {
        "selections": [
            item("direct", "direct_competitor", 3),
            *[item(f"background-{index}", "background", 3) for index in range(5)],
            item("weak", "same_problem_different_method", 0),
        ]
    }

    selections = _normalize_selections(payload, candidates, 10)

    assert [item["candidate_id"] for item in selections] == [
        "direct",
        "background-0",
        "background-1",
        "background-2",
    ]
    assert all(item["combined_score"] >= 45 for item in selections)
