import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.engine import Base
from app.db.evidence_dao import EvidenceHubDAO
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.candidate_inbox_service import CandidateInboxService, FastNewsCatalogService
from app.services.evidence_hub_service import EvidenceHubService
from app.services.fastwrite_handoff_service import EvidenceBundleService, FastWriteHandoffService


TASK_A = "11111111-1111-4111-8111-111111111111"
TASK_B = "22222222-2222-4222-8222-222222222222"


def make_dao():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return EvidenceHubDAO(sessionmaker(bind=engine, expire_on_commit=False))


def write_paper(artifacts, task_id, title, text, *, summary=""):
    artifacts.write_result(task_id, {
        "paper_task": True,
        "paper_document": {
            "id": task_id,
            "title": title,
            "authors": ["Ada Lovelace"],
            "year": 2026,
            "doi": f"10.1000/{task_id[:4]}",
            "source_url": "https://example.org/paper.pdf",
            "content_hash": f"hash-{task_id}",
            "pages": [{"page": 1, "text": text, "start": 0, "end": len(text)}],
            "page_count": 1,
        },
        "insights": {
            "personal_summary": {"content": summary} if summary else {},
            "reading_report": {},
        },
    })


def test_annotations_are_exact_atomic_and_reloadable(tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    text = "Alpha evidence on page one."
    write_paper(artifacts, TASK_A, "Alpha", text)
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")

    created = hub.create_annotation(TASK_A, {
        "page": 1,
        "start_offset": 6,
        "end_offset": 14,
        "exact_quote": "evidence",
        "note": "initial",
    })
    assert created["source_hash"] == f"hash-{TASK_A}"
    assert hub.list_annotations(TASK_A)[0]["exact_quote"] == "evidence"

    updated = hub.update_annotation(TASK_A, created["id"], {"note": "edited"})
    assert updated["note"] == "edited"
    hub.delete_annotation(TASK_A, created["id"])
    assert hub.list_annotations(TASK_A) == []

    try:
        hub.create_annotation(TASK_A, {
            "page": 1,
            "start_offset": 0,
            "end_offset": 5,
            "exact_quote": "wrong",
            "note": "",
        })
    except ValueError as exc:
        assert "不匹配" in str(exc)
    else:
        raise AssertionError("mismatched exact quote should be rejected")


def test_candidate_formats_and_dedup_priority(tmp_path):
    dao = make_dao()
    service = CandidateInboxService(dao=dao, artifacts=PaperArtifactRepository(tmp_path / "notes"))
    first = service.import_fastinsight({
        "best": {
            "title": "Verified Paper",
            "authors": ["A", "B"],
            "doi": "https://doi.org/10.1000/ABC",
            "url": "https://example.org/paper?utm_source=test",
            "score": 0.98,
        },
        "warnings": ["metadata only"],
    })[0]
    duplicate = service.import_fastinsight({
        "title": "Different title, same DOI",
        "doi": "doi:10.1000/abc",
        "url": "https://another.example/paper",
    })[0]

    assert first["producer"] == "fastinsight"
    assert first["warnings"] == ["metadata only"]
    assert duplicate["id"] == first["id"]
    assert duplicate["deduplicated"] is True
    assert len(dao.list_candidates()) == 1


def test_fastnews_commit_etag_cache_and_offline_fallback(tmp_path):
    commit = "a" * 40
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if request.url.path.endswith("/commits/main"):
            if request.headers.get("if-none-match") == '"catalog-v1"':
                return httpx.Response(304, request=request)
            return httpx.Response(200, json={"sha": commit}, headers={"etag": '"catalog-v1"'}, request=request)
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"tree": [{"path": "top-conf/data/conferences/test.jsonl"}]}, request=request)
        return httpx.Response(200, text=json.dumps({
            "_id": "paper-1",
            "title": "Catalog Paper",
            "link": "https://example.org/catalog-paper",
            "author": "A and B",
            "source": "TEST 2026",
        }) + "\n", request=request)

    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler), headers=kwargs.get("headers"))

    service = FastNewsCatalogService(tmp_path / "fastnews.json", client_factory=factory)
    fresh = service.catalog()
    cached = service.catalog()

    assert fresh["commit"] == commit
    assert fresh["entries"][0]["title"] == "Catalog Paper"
    assert cached["cache_hit"] is True
    assert any(request.headers.get("if-none-match") == '"catalog-v1"' for request in calls)

    def failing_factory(**_kwargs):
        def fail(request):
            raise httpx.ConnectError("offline", request=request)
        return httpx.Client(transport=httpx.MockTransport(fail))

    offline = FastNewsCatalogService(tmp_path / "fastnews.json", client_factory=failing_factory).catalog(force=True)
    assert offline["stale"] is True
    assert offline["commit"] == commit


def test_topic_synthesis_requires_two_distinct_papers_and_closes_quotes(tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    write_paper(artifacts, TASK_A, "Alpha", "Alpha method is exact.")
    write_paper(artifacts, TASK_B, "Beta", "Beta method is exact.")
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    topic = hub.create_topic({"question": "Can the idea work?", "user_hypotheses": ["It scales"]})
    hub.add_topic_paper(topic["id"], TASK_A)
    hub.add_topic_paper(topic["id"], TASK_B)
    hub.add_evidence(topic["id"], {"task_id": TASK_A, "page": 1, "exact_quote": "Alpha method is exact.", "role": "method"})
    hub.add_evidence(topic["id"], {"task_id": TASK_B, "page": 1, "exact_quote": "Beta method is exact.", "role": "method"})

    synthesis = hub.create_synthesis(topic["id"], {"proposed": {
        "common_reports": [{
            "statement": "领域共识 supports the method",
            "citations": [
                {"task_id": TASK_A, "page": 1, "exact_quote": "Alpha method is exact."},
                {"task_id": TASK_B, "page": 1, "exact_quote": "Beta method is exact."},
                {"task_id": TASK_B, "page": 1, "exact_quote": "hallucinated"},
            ],
        }],
        "differences": [],
        "conflicts": [],
    }})

    assert len(synthesis["common_reports"]) == 1
    assert "领域共识" not in synthesis["common_reports"][0]["statement"]
    assert len(synthesis["common_reports"][0]["citations"]) == 2
    assert synthesis["user_hypotheses"] == ["It scales"]


def test_topic_synthesis_uses_selected_model_and_binds_evidence_ids(monkeypatch, tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    write_paper(artifacts, TASK_A, "Alpha", "Alpha method is exact.")
    write_paper(artifacts, TASK_B, "Beta", "Beta method is exact.")
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    topic = hub.create_topic({"question": "Can the idea work?", "user_hypotheses": ["It scales"]})
    hub.add_topic_paper(topic["id"], TASK_A)
    hub.add_topic_paper(topic["id"], TASK_B)
    hub.add_evidence(topic["id"], {"task_id": TASK_A, "page": 1, "exact_quote": "Alpha method is exact.", "role": "method"})
    hub.add_evidence(topic["id"], {"task_id": TASK_B, "page": 1, "exact_quote": "Beta method is exact.", "role": "method"})
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            content = json.dumps({
                "common_reports": [{
                    "statement": "两篇论文都给出了可执行的方法，但具体设计不同。",
                    "evidence_ids": ["E1", "E2", "E99"],
                }],
                "differences": [{"statement": "Alpha 与 Beta 采用不同方法。", "evidence_ids": ["E1", "E2"]}],
                "conflicts": [],
                "evidence_gaps": ["缺少统一指标。"],
                "idea_feasibility": {
                    "problem": "比较两种方法是否可扩展。",
                    "what_papers_achieved": [{"statement": "已有两种方法原型。", "evidence_ids": ["E1", "E2"]}],
                    "counterexamples_and_limitations": [{"statement": "当前证据未覆盖规模实验。", "evidence_ids": ["E1"]}],
                    "minimum_validation_experiment": "固定数据集，比较两种方法的准确率与耗时。",
                    "evidence_to_read": ["E1", "补充规模实验。"],
                },
            })
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="selected-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(
        "app.services.evidence_hub_service.GPTProvider.create",
        lambda **kwargs: fake_gpt,
    )

    synthesis = hub.create_synthesis(topic["id"], {
        "provider_id": "selected-provider",
        "model_name": "selected-model",
    })

    assert synthesis["kind"] == "model"
    assert synthesis["model"] == {"provider_id": "selected-provider", "model_name": "selected-model"}
    assert len(synthesis["common_reports"][0]["citations"]) == 2
    assert len(synthesis["idea_feasibility"]["what_papers_achieved"][0]["citations"]) == 2
    assert synthesis["idea_feasibility"]["minimum_validation_experiment"].startswith("固定数据集")
    assert synthesis["idea_feasibility"]["evidence_to_read"] == ["补充规模实验。"]
    assert calls[0]["model"] == "selected-model"
    assert "只负责把程序给出的跨论文证据整理成结构化比较" in calls[0]["messages"][0]["content"]
    model_context = json.loads(calls[0]["messages"][1]["content"])
    assert len(model_context["evidence"]) >= 2
    assert all(item.get("verbatim_evidence") for item in model_context["evidence"])


def test_topic_evidence_classifier_selects_ids_and_preserves_old_evidence_on_invalid_rerun(monkeypatch, tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    text = " ".join([
        "This study asks whether compact evaluations can preserve a reliable model ranking across tasks.",
        "We propose a pairwise comparison method that estimates a global ordering from local judgments.",
        "We evaluate twelve models on three datasets and report Kendall correlation against the full benchmark.",
        "A limitation is that the human study includes only seven annotators and may not generalize broadly.",
        "The final analysis connects behavioral ordering to practical value-alignment audits in deployment.",
    ])
    write_paper(artifacts, TASK_A, "Flexible evidence", text)
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    topic = hub.create_topic({"question": "Reliable evaluation"})
    hub.add_topic_paper(topic["id"], TASK_A)
    invalid = {"enabled": False}
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            context = json.loads(kwargs["messages"][1]["content"])
            if invalid["enabled"]:
                content = json.dumps({
                    "selections": [{"candidate_id": "C999", "roles": ["experiment"], "confidence": 0.9}],
                    "unresolved_roles": [],
                })
            else:
                selections = []
                for candidate in context["candidates"]:
                    quote = candidate["verbatim_evidence"]
                    role = None
                    if "asks whether" in quote:
                        role = "question"
                    elif "propose a pairwise" in quote:
                        role = "method"
                    elif "evaluate twelve models" in quote:
                        role = "experiment"
                    elif "limitation is" in quote:
                        role = "limitation"
                    elif "final analysis" in quote:
                        role = "other"
                    if role:
                        selections.append({
                            "candidate_id": candidate["candidate_id"],
                            "roles": [role],
                            "confidence": 0.8,
                            "reason": "verbatim role evidence",
                        })
                content = json.dumps({"selections": selections, "unresolved_roles": []})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="cheap-classifier",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(
        "app.services.evidence_hub_service.GPTProvider.create",
        lambda **_kwargs: fake_gpt,
    )

    result = hub.extract_topic_evidence(topic["id"], {
        "provider_id": "deepseek",
        "model_name": "cheap-classifier",
        "max_candidates": 80,
    })
    run = result["runs"][0]
    assert run["status"] == "completed"
    assert run["prompt_version"] == "topic-evidence-id-selection-v2"
    assert run["strategy_version"] == "page-balanced-verbatim-candidates-v4"
    assert run["fallback_used"] is False
    assert run["selected_by_role"] == {
        "question": 1,
        "method": 1,
        "experiment": 1,
        "limitation": 1,
        "other": 1,
    }
    matrix = result["topic"]["evidence_matrix"]
    assert all(len(matrix[role]) == 1 for role in ("question", "method", "experiment", "limitation", "other"))
    assert all(item["source_kind"] == "model_classified" for items in matrix.values() for item in items)
    assert all(item["exact_quote"] in text for items in matrix.values() for item in items)
    classifier_context = json.loads(calls[0]["messages"][1]["content"])
    assert classifier_context["limits"]["max_candidates"] == 80
    assert all("candidate_id" in item and "page" in item for item in classifier_context["candidates"])

    previous_ids = {item["id"] for items in matrix.values() for item in items}
    invalid["enabled"] = True
    failed = hub.extract_topic_evidence(topic["id"], {
        "provider_id": "deepseek",
        "model_name": "cheap-classifier",
        "max_candidates": 80,
    })
    assert failed["runs"][0]["status"] == "failed"
    assert failed["runs"][0]["run_id"]
    assert failed["runs"][0]["candidate_count"] == 5
    assert failed["runs"][0]["fallback_reason"] == "model_call_or_validation_failed"
    assert failed["runs"][0]["fallback_used"] is False
    retained_ids = {
        item["id"]
        for items in failed["topic"]["evidence_matrix"].values()
        for item in items
        if item["source_kind"] == "model_classified"
    }
    assert retained_ids == previous_ids


def test_topic_evidence_candidates_remove_pdf_chrome_and_numeric_figure_noise(tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    paper = {
        "pages": [
            {
                "page": 1,
                "text": (
                    "Published as a conference paper at ICLR 2026 "
                    "HOW RELIABLE IS LANGUAGE MODEL MICRO-BENCHMARKING?\n"
                    "Published as a conference paper at ICLR 2026 "
                    "We introduce a reliability measure that identifies the minimum performance gap "
                    "needed for a micro-benchmark to preserve pairwise model rankings."
                ),
            },
            {
                "page": 2,
                "text": (
                    "Published as a conference paper at ICLR 2026 "
                    "0.2 0.4 0.6 0.8 1 Agreement 10 25 50 100 250 500 1000 "
                    "0 5 10 15 20 25 MDAD 2% 4% 8% 16% 24% 32% 40%"
                ),
            },
            {
                "page": 3,
                "text": (
                    "4.2 PROMPTED DISPOSITIONS We hypothesize that language models have measurable "
                    "dispositional tendencies that persist across prompts."
                ),
            },
        ],
    }

    candidates = hub._classification_candidates(TASK_A, paper, {}, 80)

    assert {item["verbatim_evidence"] for item in candidates} == {
        "We introduce a reliability measure that identifies the minimum performance gap "
        "needed for a micro-benchmark to preserve pairwise model rankings.",
        "We hypothesize that language models have measurable dispositional tendencies that persist across prompts.",
    }
    assert all("Published as a conference paper" not in item["verbatim_evidence"] for item in candidates)


def test_report_derived_matrix_is_atomically_rebuilt_with_clean_quotes(tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    text = (
        "Published as a conference paper at ICLR 2026 "
        "We propose a calibrated reliability measure for pairwise model rankings."
    )
    write_paper(artifacts, TASK_A, "Clean report evidence", text)

    def attach_report(result):
        result["insights"]["reading_report"] = {
            "key_questions": [{
                "question": "What is measured?",
                "evidence": [{
                    "page_start": 1,
                    "exact_quote": text,
                }],
            }],
        }
        return result

    artifacts.update_result(TASK_A, attach_report)
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    topic = hub.create_topic({"question": "Reliable rankings"})
    hub.add_topic_paper(topic["id"], TASK_A)

    evidence = [
        item for item in hub.get_topic(topic["id"])["evidence_items"]
        if item["source_kind"] == "report"
    ]
    assert [item["exact_quote"] for item in evidence] == [
        "We propose a calibrated reliability measure for pairwise model rankings."
    ]

    artifacts.update_result(TASK_A, lambda result: {
        **result,
        "insights": {**result["insights"], "reading_report": {"key_questions": []}},
    })
    hub.refresh_topic_evidence(topic["id"])
    assert not [
        item for item in hub.get_topic(topic["id"])["evidence_items"]
        if item["source_kind"] == "report"
    ]


def test_topic_chat_is_scoped_to_members_and_closes_page_sources(monkeypatch, tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    write_paper(artifacts, TASK_A, "Alpha", "Alpha paper presents a staged attack evaluation.")
    write_paper(artifacts, TASK_B, "Beta", "Beta paper compares two safety filters.")
    write_paper(artifacts, "33333333-3333-4333-8333-333333333333", "Outside", "Outside secret evidence.")
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    topic = hub.create_topic({"question": "Jailbreak attacks"})
    hub.add_topic_paper(topic["id"], TASK_A)
    hub.add_topic_paper(topic["id"], TASK_B)
    cross_language_sources = hub._topic_chat_sources(
        hub.get_topic(topic["id"]),
        "请分别说明两篇论文的方法",
        "question",
    )
    assert {source["task_id"] for source in cross_language_sources} == {TASK_A, TASK_B}
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            content = "Alpha 论文给出分阶段评估 [S1]；Beta 论文比较两种过滤器 [S2]。"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="test-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(
        "app.services.evidence_hub_service.GPTProvider.create",
        lambda **_kwargs: fake_gpt,
    )

    result = hub.ask_topic(topic["id"], {
        "question": "",
        "mode": "summary",
        "history": [{"role": "assistant", "content": "上一轮回答 [S9]"}],
        "provider_id": "provider",
        "model_name": "model",
    })

    assert result["grounding_status"] == "source_grounded"
    assert {source["task_id"] for source in result["sources"]} == {TASK_A, TASK_B}
    assert all(source["page_start"] == 1 for source in result["sources"])
    assert {source["exact_quote"] for source in result["sources"]} == {
        "Alpha paper presents a staged attack evaluation",
        "Beta paper compares two safety filters",
    }
    assert "Outside secret evidence" not in calls[0]["messages"][0]["content"]
    assert "每篇论文至少使用一个来源编号" in calls[0]["messages"][-1]["content"]
    assert "不要生成逐字引文" in calls[0]["messages"][0]["content"]
    assert calls[0]["messages"][1]["content"] == "上一轮回答"
    assert "response_format" not in calls[0]


def test_topic_summary_rejects_single_paper_coverage(monkeypatch, tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    write_paper(artifacts, TASK_A, "Alpha", "Alpha paper presents a staged attack evaluation.")
    write_paper(artifacts, TASK_B, "Beta", "Beta paper compares two safety filters.")
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    topic = hub.create_topic({"question": "Jailbreak attacks"})
    hub.add_topic_paper(topic["id"], TASK_A)
    hub.add_topic_paper(topic["id"], TASK_B)

    class Completions:
        def create(self, **_kwargs):
            content = "只总结了 Alpha 论文 [S1]。"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="test-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(
        "app.services.evidence_hub_service.GPTProvider.create",
        lambda **_kwargs: fake_gpt,
    )

    with pytest.raises(ValueError, match="至少两篇成员论文"):
        hub.ask_topic(topic["id"], {
            "question": "",
            "mode": "summary",
            "history": [],
            "provider_id": "provider",
            "model_name": "model",
        })


def test_topic_chat_rejects_unknown_model_source_id(monkeypatch, tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    write_paper(artifacts, TASK_A, "Alpha", "Exact source sentence.")
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    topic = hub.create_topic({"question": "Source closure"})
    hub.add_topic_paper(topic["id"], TASK_A)

    class Completions:
        def create(self, **_kwargs):
            content = "模型引用了不存在的来源 [S99]。"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    fake_gpt = SimpleNamespace(
        model="test-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )
    monkeypatch.setattr(
        "app.services.evidence_hub_service.GPTProvider.create",
        lambda **_kwargs: fake_gpt,
    )

    with pytest.raises(ValueError, match="无效或缺失"):
        hub.ask_topic(topic["id"], {
            "question": "source",
            "mode": "question",
            "history": [],
            "provider_id": "provider",
            "model_name": "model",
        })


class PartialFastWrite:
    base_url = "http://127.0.0.1:3003"

    def __init__(self):
        self.calls = []
        self.fail_once = True

    def projects(self):
        return [{"id": "project-1", "name": "Paper"}]

    def create_file(self, project_id, path, content):
        self.calls.append(path)
        if path.endswith("citations.json") and self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary outage")


def test_fastwrite_partial_retry_is_idempotent_and_manifest_is_last(tmp_path):
    dao = make_dao()
    artifacts = PaperArtifactRepository(tmp_path / "notes")
    write_paper(artifacts, TASK_A, "Alpha", "Alpha evidence.", summary="My note")
    hub = EvidenceHubService(dao, artifacts, tmp_path / "integrations")
    hub.create_annotation(TASK_A, {
        "page": 1,
        "start_offset": 0,
        "end_offset": len("Alpha evidence."),
        "exact_quote": "Alpha evidence.",
        "note": "annotation",
    })
    bundles = EvidenceBundleService(dao, artifacts, hub, tmp_path / "integrations")
    client = PartialFastWrite()
    service = FastWriteHandoffService(dao, bundles, client)

    failed = service.create({
        "project_id": "project-1",
        "task_id": TASK_A,
        "include_user_notes": True,
    })
    assert failed["status"] == "failed"
    assert failed["successful_files"] == ["evidence.md"]

    completed = service.retry(failed["id"])
    assert completed["status"] == "completed"
    assert client.calls.count(f"{completed['target_path']}/evidence.md") == 1
    assert client.calls[-1].endswith("manifest.json")
    repeated = service.create({
        "project_id": "project-1",
        "task_id": TASK_A,
        "include_user_notes": True,
    })
    assert repeated["id"] == completed["id"]
    assert service.download(completed["id"])[1].startswith(b"PK")
