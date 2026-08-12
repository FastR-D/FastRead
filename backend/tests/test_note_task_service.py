import os
from datetime import datetime

from app.enmus.task_status_enums import TaskStatus
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.note_task_service import NoteTaskService
from app.services.verification import pipeline


def test_get_task_status_returns_success_result_when_status_file_succeeds(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("task-a", {"markdown": "# Note", "transcript": {}, "audio_meta": {}})
    repo.write_status("task-a", TaskStatus.SUCCESS, "done")

    payload = service.get_task_status("task-a")

    assert payload["status"] == TaskStatus.SUCCESS.value
    assert payload["message"] == "done"
    assert payload["id"] == "task-a"
    assert payload["task_id"] == "task-a"
    assert payload["result"]["markdown"] == "# Note"
    assert payload["createdAt"] == 0
    assert payload["updatedAt"] == 0


def test_get_task_status_classifies_failed_status(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_status("task-a", TaskStatus.FAILED, "cookie expired")

    payload = service.get_task_status("task-a")

    assert payload["status"] == TaskStatus.FAILED.value
    assert payload["result"] is None
    assert payload["error"]["category"] == "cookie"


def test_list_tasks_merges_db_and_file_backed_tasks(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("db-task", {
        "markdown": "> 来源链接：http://fallback",
        "transcript": {"full_text": "db transcript", "segments": []},
        "audio_meta": {"title": "cached"},
    })
    repo.write_result("file-task", {
        "markdown": "> 来源链接：http://file",
        "transcript": {"full_text": "file transcript", "segments": []},
        "audio_meta": {"title": "file"},
    })

    monkeypatch.setattr(
        "app.services.note_task_service.list_video_tasks",
        lambda: [
            {
                "task_id": "db-task",
                "video_url": "http://db",
                "created_at": datetime.fromtimestamp(10),
                "collection_folder": "",
                "collection_tags": "a, b",
                "collection_note": "note",
                "title": "db",
                "cover_url": "cover",
                "updated_at": datetime.fromtimestamp(11),
            }
        ],
    )

    tasks = service.list_tasks()

    assert [task["id"] for task in tasks] == ["file-task", "db-task"]
    assert tasks[1]["videoUrl"] == "http://db"
    assert tasks[1]["collection"]["tags"] == ["a", "b"]
    assert tasks[1]["result"]["markdown"].startswith("> 来源链接")
    assert tasks[1]["transcript"]["full_text"] == "db transcript"
    assert tasks[1]["updatedAt"] == 11
    assert tasks[0]["result"]["audio_meta"]["title"] == "file"


def test_verify_task_online_reports_missing_result(tmp_path):
    service = NoteTaskService(NoteArtifactRepository(tmp_path))

    result = service.verify_task_online(task_id="missing")

    assert result == {"ok": False, "code": 404, "message": "任务结果不存在"}


def test_verify_task_online_updates_existing_verification(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("task-a", {
        "markdown": "# Note",
        "transcript": {"full_text": "claim context"},
        "audio_meta": {"title": "title", "raw_info": {}},
        "insights": {"verification": {"claims": [{"text": "claim"}]}},
    })

    def fake_verify(verification, **kwargs):
        assert kwargs["max_claims"] == 20
        assert "claim context" in kwargs["context"]
        return {"claims": verification["claims"], "online": True}

    monkeypatch.setattr("app.services.note_task_service.verify_claims_online", fake_verify)

    result = service.verify_task_online(task_id="task-a", max_claims=99)

    assert result["ok"] is True
    assert result["data"]["insights"]["verification"]["online"] is True
    assert repo.read_result("task-a")["insights"]["verification"]["online"] is True


def test_verify_task_online_attaches_claim_artifact_refs(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("task-a", {
        "markdown": "# Note",
        "transcript": {"full_text": "claim context"},
        "audio_meta": {"title": "title", "raw_info": {}},
        "insights": {"verification": {"claims": [{"claim": "claim"}]}},
    })

    def fake_verify(verification, **kwargs):
        callback = kwargs["stage_callback"]
        callback({
            "claim_id": "claim-1-test",
            "stage": "claim_started",
            "atomic_claim": "claim",
            "claim_facts": {},
            "queries": ["claim"],
        })
        callback({
            "claim_id": "claim-1-test",
            "stage": "claim_completed",
            "result": {"claim_id": "claim-1-test", "verdict": "supported", "confidence": 95},
        })
        claim = verification["claims"][0]
        claim["online"] = {"claim_id": "claim-1-test", "audit": {}}
        return {
            "claims": verification["claims"],
            "result": {"claims": verification["claims"], "audit": {}},
        }

    monkeypatch.setattr("app.services.note_task_service.verify_claims_online", fake_verify)

    result = service.verify_task_online(task_id="task-a")
    saved = repo.read_result("task-a")
    online = saved["insights"]["verification"]["claims"][0]["online"]
    artifact = repo.read_verification_claim_artifact("task-a", "claim-1-test")

    assert result["ok"] is True
    assert artifact["status"] == "completed"
    assert online["claim_artifact_path"].endswith("claim-1-test.json")
    assert online["audit"]["claim_artifact_path"] == online["claim_artifact_path"]
    assert saved["verification_result"]["audit"]["artifact_root"].endswith(os.path.join("_verification", "task-a"))


def test_delete_task_artifacts_deletes_files_and_calls_delete_index(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    calls = []

    class FakeVectorStore:
        def delete_index(self, task_id):
            calls.append(task_id)

    def fake_factory():
        return FakeVectorStore()

    service = NoteTaskService(repo, vector_store_factory=fake_factory)

    repo.write_result("task-x", {"markdown": "# Note"})
    repo.write_status("task-x", "SUCCESS", "")
    repo.write_transcript_cache("task-x", {"full_text": "t"})
    repo.write_audio_cache("task-x", {"title": "test"})
    repo.write_markdown_cache("task-x", "# md")
    repo.write_verification_claim_artifact("task-x", "claim-1", {"status": "completed"})

    assert repo.result_path("task-x").exists()
    assert repo.status_path("task-x").exists()

    deleted = service.delete_task_artifacts("task-x")

    assert deleted == 6
    assert not repo.result_path("task-x").exists()
    assert not repo.status_path("task-x").exists()
    assert not repo.transcript_cache_path("task-x").exists()
    assert not repo.audio_cache_path("task-x").exists()
    assert not repo.markdown_cache_path("task-x").exists()
    assert not repo.verification_task_dir("task-x").exists()
    assert calls == ["task-x"]


def test_delete_task_artifacts_swallows_vector_delete_failure(tmp_path):
    repo = NoteArtifactRepository(tmp_path)

    class FailingVectorStore:
        def delete_index(self, task_id):
            raise RuntimeError("chromadb connection lost")

    def failing_factory():
        return FailingVectorStore()

    service = NoteTaskService(repo, vector_store_factory=failing_factory)
    repo.write_result("task-y", {"markdown": "# Note"})

    deleted = service.delete_task_artifacts("task-y")

    assert deleted == 1
    assert not repo.result_path("task-y").exists()


def test_verification_stage_writer_persists_claim_artifact(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    writer = service._verification_stage_writer("verify-task")

    writer({
        "claim_id": "claim-1-abc",
        "stage": "claim_started",
        "atomic_claim": "鸡蛋中含有超过1500种独特蛋白质",
        "claim_facts": {"domain_type": "science"},
        "queries": ["egg 1500 proteins"],
        "context_chars": 12,
    })
    writer({
        "claim_id": "claim-1-abc",
        "stage": "search_completed",
        "queries": ["egg 1500 proteins"],
        "search_providers": ["fixture"],
        "raw_result_count": 1,
        "raw_results": [{"url": "https://pubmed.ncbi.nlm.nih.gov/1/"}],
    })
    writer({
        "claim_id": "claim-1-abc",
        "stage": "source_fetched",
        "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
        "source": {
            "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "domain": "pubmed.ncbi.nlm.nih.gov",
            "trust_tier": "A",
            "fetch_status": "ok",
            "content_hash": "hash",
        },
        "fetch_status": "ok",
        "evidence_added": 1,
    })
    writer({
        "claim_id": "claim-1-abc",
        "stage": "claim_completed",
        "result": {
            "claim_id": "claim-1-abc",
            "verdict": "supported",
            "confidence": 95,
            "risk_flags": [],
            "sources": [{"source_id": "src-a"}],
            "evidence": [{"evidence_id": "ev-a"}],
        },
    })

    artifact = repo.read_verification_claim_artifact("verify-task", "claim-1-abc")

    assert artifact["status"] == "completed"
    assert artifact["atomic_claim"] == "鸡蛋中含有超过1500种独特蛋白质"
    assert artifact["search"]["raw_result_count"] == 1
    assert artifact["fetches"][0]["trust_tier"] == "A"
    assert artifact["result"]["verdict"] == "supported"
    assert artifact["audit_ids"] == {
        "claim_id": "claim-1-abc",
        "source_ids": ["src-a"],
        "evidence_ids": ["ev-a"],
    }
    assert [stage["stage"] for stage in artifact["stages"]] == [
        "claim_started",
        "search_completed",
        "source_fetched",
        "claim_completed",
    ]


def test_verification_cache_roundtrip_is_isolated_from_task_results(tmp_path):
    repo = NoteArtifactRepository(tmp_path)

    repo.write_verification_cache("serp", "serp-abc", {"raw_results": [{"url": "https://example.com"}]})

    assert repo.read_verification_cache("serp", "serp-abc") == {
        "raw_results": [{"url": "https://example.com"}],
    }
    assert list(repo.iter_result_files()) == []


def test_filesystem_verification_cache_reused_across_service_instances(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    claim = "鸡蛋中含有超过1500种独特蛋白质"
    url = "https://pubmed.ncbi.nlm.nih.gov/1/"
    result = {"title": "Egg protein atlas", "url": url, "snippet": "snippet"}
    snapshot = {
        "url": url,
        "canonical_url": url,
        "title": "Egg protein atlas",
        "retrieved_at": "2026-06-20T00:00:00Z",
        "fetch_status": "ok",
        "source_type": "web",
        "text": "鸡蛋 蛋白质组 研究显示鸡蛋中含有超过1500种独特蛋白质。",
    }
    calls = {"search": 0, "fetch": 0, "evidence": 0}

    def fake_search(_queries, _limit, _claim, trace):
        calls["search"] += 1
        if trace is not None:
            trace.append("fixture")
        return [result]

    def fake_fetch(_url, _result=None):
        calls["fetch"] += 1
        return snapshot

    def fake_extract(_claim, source, _text):
        calls["evidence"] += 1
        return [{
            "source_url": source["url"],
            "passage": "body support",
            "stance": "support",
            "claim_element": "overall",
            "confidence": 80,
            "extraction_method": "fixture",
        }]

    monkeypatch.setattr(pipeline.evidence_service, "extract_evidence_for_claim", fake_extract)

    first = pipeline.verify_claim(
        claim,
        search_fn=fake_search,
        fetch_fn=fake_fetch,
        cache=NoteTaskService(repo)._verification_cache(),
    )
    second = pipeline.verify_claim(
        claim,
        search_fn=fake_search,
        fetch_fn=fake_fetch,
        cache=NoteTaskService(repo)._verification_cache(),
    )

    assert calls == {"search": 1, "fetch": 1, "evidence": 1}
    assert first["audit"]["cache"]["serp"]["hit"] is False
    assert second["audit"]["cache"]["serp"]["hit"] is True
    assert second["audit"]["cache"]["snapshots"][0]["hit"] is True
    assert second["audit"]["cache"]["evidence"][0]["hit"] is True


def test_reusable_verification_claim_results_reads_completed_artifacts(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    verification = {
        "claims": [
            {"claim": "claim one", "priority": 100},
            {"claim": "claim two", "priority": 90},
        ]
    }

    repo.write_verification_claim_artifact(
        "task-a",
        "claim-1-8357573a4f",
        {"status": "completed", "result": {"verdict": "supported"}},
    )
    repo.write_verification_claim_artifact(
        "task-a",
        "claim-2-7284723c33",
        {"status": "search_failed", "result": {"verdict": "data_void"}},
    )

    reusable = service._reusable_verification_claim_results("task-a", verification)

    assert reusable == {"claim one": {"verdict": "supported"}}


def test_reusable_verification_claim_results_reads_online_claim_id_when_order_changes(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    claim_one = "claim one"
    claim_two = "claim two"
    historical_claim_one_id = pipeline.claim_id_for(claim_one, 0)
    verification = {
        "claims": [
            {"claim": claim_one, "priority": 1, "online": {"claim_id": historical_claim_one_id}},
            {"claim": claim_two, "priority": 100},
        ]
    }
    repo.write_verification_claim_artifact(
        "task-a",
        historical_claim_one_id,
        {
            "status": "completed",
            "atomic_claim": claim_one,
            "result": {"atomic_claim": claim_one, "verdict": "supported"},
        },
    )

    reusable = service._reusable_verification_claim_results("task-a", verification)

    assert reusable == {claim_one: {"atomic_claim": claim_one, "verdict": "supported"}}


def test_rerun_verification_task_reuses_completed_claim_artifacts(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("task-a", {
        "verification_task": True,
        "verification_input": {"text": "claim one", "max_claims": 50},
        "insights": {"verification": {"claims": [{"claim": "claim one", "priority": 100}]}},
    })
    repo.write_verification_claim_artifact(
        "task-a",
        "claim-1-8357573a4f",
        {
            "status": "completed",
            "result": {
                "claim_id": "claim-1-8357573a4f",
                "atomic_claim": "claim one",
                "verdict": "supported",
                "confidence": 95,
                "sources": [],
                "evidence": [],
                "risk_flags": [],
                "audit": {"queries": ["claim one"]},
            },
        },
    )
    captured = {}

    def fake_verify(verification, **kwargs):
        captured["reuse_claim_results"] = kwargs["reuse_claim_results"]
        claim = verification["claims"][0]
        claim["online"] = {
            "claim_id": "claim-1-8357573a4f",
            "audit": {"reused_from_claim_artifact": True},
        }
        return {"claims": verification["claims"], "result": {"claims": verification["claims"], "audit": {}}}

    monkeypatch.setattr("app.services.note_task_service.verify_claims_online", fake_verify)

    result = service.rerun_verification_task("task-a")

    assert result["ok"] is True
    assert captured["reuse_claim_results"]["claim one"]["verdict"] == "supported"


def test_execute_url_verification_task_records_input_source_audit(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    task_id = "url-task"
    input_url = "https://example.org/claim"
    repo.write_result(task_id, {
        "verification_task": True,
        "verification_input": {
            "text": "",
            "url": input_url,
            "max_claims": 50,
            "verification_depth": "deep",
        },
        "insights": {"verification": {"claims": [{"claim": "示例主张", "priority": 100}]}},
    })

    def fake_fetch(url, _result=None):
        assert url == input_url
        return {
            "url": "https://www.example.org/claim",
            "canonical_url": "https://example.org/claim",
            "title": "Source title",
            "publisher": "Example Publisher",
            "author": "Reporter",
            "published_at": "2026-06-20",
            "retrieved_at": "2026-06-21T00:00:00+00:00",
            "fetch_status": "ok",
            "source_type": "web",
            "redirect_chain": [input_url, "https://www.example.org/claim"],
            "text": "示例主张 来自原始页面正文。",
        }

    def fake_verify(verification, **kwargs):
        assert "原始页面正文" in kwargs["context"]
        claim = verification["claims"][0]
        claim["online"] = {"claim_id": "claim-1-url", "audit": {}}
        return {
            "claims": verification["claims"],
            "result": {"claims": verification["claims"], "audit": {"version": 2}},
        }

    monkeypatch.setattr("app.services.note_task_service.verification_fetching.fetch_source_snapshot", fake_fetch)
    monkeypatch.setattr("app.services.note_task_service.verify_claims_online", fake_verify)

    service.execute_verification_task(task_id)
    saved = repo.read_result(task_id)
    audit = saved["verification_result"]["audit"]["input_source"]

    assert saved["transcript"]["full_text"] == "示例主张 来自原始页面正文。"
    assert audit["requested_url"] == input_url
    assert audit["fetched_url"] == "https://www.example.org/claim"
    assert audit["canonical_url"] == "https://example.org/claim"
    assert audit["fetch_status"] == "ok"
    assert audit["text_chars"] == len("示例主张 来自原始页面正文。")
    assert audit["redirect_chain"] == [input_url, "https://www.example.org/claim"]


def test_rerun_verification_claim_excludes_target_claim_artifact(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("task-a", {
        "verification_task": True,
        "verification_input": {"text": "claim one\nclaim two", "max_claims": 50},
        "insights": {
            "verification": {
                "claims": [
                    {"claim": "claim one", "priority": 100},
                    {"claim": "claim two", "priority": 90},
                ]
            }
        },
    })
    repo.write_verification_claim_artifact(
        "task-a",
        "claim-1-8357573a4f",
        {
            "status": "completed",
            "result": {
                "claim_id": "claim-1-8357573a4f",
                "atomic_claim": "claim one",
                "verdict": "supported",
                "confidence": 95,
                "sources": [],
                "evidence": [],
                "risk_flags": [],
                "audit": {"queries": ["claim one"]},
            },
        },
    )
    repo.write_verification_claim_artifact(
        "task-a",
        "claim-2-7284723c33",
        {
            "status": "completed",
            "result": {
                "claim_id": "claim-2-7284723c33",
                "atomic_claim": "claim two",
                "verdict": "refuted",
                "confidence": 90,
                "sources": [],
                "evidence": [],
                "risk_flags": [],
                "audit": {"queries": ["claim two"]},
            },
        },
    )
    captured = {}

    def fake_verify(verification, **kwargs):
        captured["reuse_claim_results"] = kwargs["reuse_claim_results"]
        for index, claim in enumerate(verification["claims"]):
            claim["online"] = {
                "claim_id": f"claim-{index + 1}-{'8357573a4f' if index == 0 else '7284723c33'}",
                "audit": {},
            }
        return {"claims": verification["claims"], "result": {"claims": verification["claims"], "audit": {}}}

    monkeypatch.setattr("app.services.note_task_service.verify_claims_online", fake_verify)

    result = service.rerun_verification_claim("task-a", "claim-1-8357573a4f")

    assert result["ok"] is True
    assert "claim one" not in captured["reuse_claim_results"]
    assert captured["reuse_claim_results"]["claim two"]["verdict"] == "refuted"


def test_rerun_verification_claim_excludes_target_by_text_when_online_id_changed(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    claim_one = "claim one"
    claim_two = "claim two"
    historical_claim_one_id = pipeline.claim_id_for(claim_one, 0)
    historical_claim_two_id = pipeline.claim_id_for(claim_two, 1)
    repo.write_result("task-a", {
        "verification_task": True,
        "verification_input": {"text": "claim one\nclaim two", "max_claims": 50},
        "insights": {
            "verification": {
                "claims": [
                    {
                        "claim": claim_one,
                        "priority": 1,
                        "online": {"claim_id": historical_claim_one_id},
                    },
                    {
                        "claim": claim_two,
                        "priority": 100,
                        "online": {"claim_id": historical_claim_two_id},
                    },
                ]
            }
        },
    })
    for claim_text, claim_id, verdict in [
        (claim_one, historical_claim_one_id, "supported"),
        (claim_two, historical_claim_two_id, "refuted"),
    ]:
        repo.write_verification_claim_artifact(
            "task-a",
            claim_id,
            {
                "status": "completed",
                "atomic_claim": claim_text,
                "result": {
                    "claim_id": claim_id,
                    "atomic_claim": claim_text,
                    "verdict": verdict,
                    "confidence": 90,
                    "sources": [],
                    "evidence": [],
                    "risk_flags": [],
                    "audit": {"queries": [claim_text]},
                },
            },
        )
    captured = {}

    def fake_verify(verification, **kwargs):
        captured["reuse_claim_results"] = kwargs["reuse_claim_results"]
        for claim in verification["claims"]:
            claim["online"] = {"claim_id": (claim.get("online") or {}).get("claim_id"), "audit": {}}
        return {"claims": verification["claims"], "result": {"claims": verification["claims"], "audit": {}}}

    monkeypatch.setattr("app.services.note_task_service.verify_claims_online", fake_verify)

    result = service.rerun_verification_claim("task-a", historical_claim_one_id)

    assert result["ok"] is True
    assert claim_one not in captured["reuse_claim_results"]
    assert captured["reuse_claim_results"][claim_two]["verdict"] == "refuted"


def test_rerun_verification_claim_rejects_stale_artifact_not_in_current_seed(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("task-a", {
        "verification_task": True,
        "verification_input": {"text": "claim one", "max_claims": 50},
        "insights": {"verification": {"claims": [{"claim": "claim one", "priority": 100}]}},
    })
    repo.write_verification_claim_artifact(
        "task-a",
        "claim-1-stale",
        {
            "status": "completed",
            "atomic_claim": "stale claim",
            "result": {"atomic_claim": "stale claim", "verdict": "supported"},
        },
    )

    def fail_execute(*_args, **_kwargs):
        raise AssertionError("stale claim rerun should not execute")

    monkeypatch.setattr(service, "execute_verification_task", fail_execute)

    result = service.rerun_verification_claim("task-a", "claim-1-stale")

    assert result == {"ok": False, "code": 404, "message": "核验主张不存在"}
