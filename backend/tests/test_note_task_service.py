from datetime import datetime

from app.enmus.task_status_enums import TaskStatus
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.note_task_service import NoteTaskService


def test_persist_prefetched_transcript_cleans_segments(tmp_path):
    service = NoteTaskService(NoteArtifactRepository(tmp_path))

    service.persist_prefetched_transcript(
        "task-a",
        {
            "segments": [
                {"start": "1.5", "end": 2, "text": " hello "},
                {"start": 2, "end": 3, "text": "   "},
                {"start": 3, "end": 4, "text": "world"},
            ],
        },
    )

    cached = service.artifacts.read_transcript_cache("task-a")
    assert cached == {
        "language": "zh",
        "full_text": "hello world",
        "segments": [
            {"start": 1.5, "end": 2.0, "text": "hello"},
            {"start": 3.0, "end": 4.0, "text": "world"},
        ],
    }


def test_persist_prefetched_transcript_rejects_empty_segments(tmp_path):
    service = NoteTaskService(NoteArtifactRepository(tmp_path))

    try:
        service.persist_prefetched_transcript("task-a", {"segments": [{"text": "  "}]})
    except ValueError as exc:
        assert "没有可用的 segments" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_get_task_status_returns_success_result_when_status_file_succeeds(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("task-a", {"markdown": "# Note", "transcript": {}, "audio_meta": {}})
    repo.write_status("task-a", TaskStatus.SUCCESS, "done")

    payload = service.get_task_status("task-a")

    assert payload["status"] == TaskStatus.SUCCESS.value
    assert payload["message"] == "done"
    assert payload["task_id"] == "task-a"
    assert payload["result"]["markdown"] == "# Note"


def test_get_task_status_classifies_failed_status(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_status("task-a", TaskStatus.FAILED, "cookie expired")

    payload = service.get_task_status("task-a")

    assert payload["status"] == TaskStatus.FAILED.value
    assert payload["error"]["category"] == "cookie"


def test_list_tasks_merges_db_and_file_backed_tasks(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    repo.write_result("db-task", {"markdown": "> 来源链接：http://fallback", "audio_meta": {"title": "cached"}})
    repo.write_result("file-task", {"markdown": "> 来源链接：http://file", "audio_meta": {"title": "file"}})

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
            }
        ],
    )

    tasks = service.list_tasks()

    assert [task["id"] for task in tasks] == ["file-task", "db-task"]
    assert tasks[1]["videoUrl"] == "http://db"
    assert tasks[1]["collection"]["tags"] == ["a", "b"]


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
