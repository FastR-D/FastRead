from app.enmus.task_status_enums import TaskStatus
from app.repositories.note_artifacts import NoteArtifactRepository


def test_result_round_trip_and_listing(tmp_path):
    repo = NoteArtifactRepository(tmp_path)

    repo.write_result("task-a", {"markdown": "hello"})
    repo.write_transcript_cache("task-a", {"full_text": "cached", "segments": []})

    assert repo.read_result("task-a") == {"markdown": "hello"}
    assert [item.task_id for item in repo.iter_result_files()] == ["task-a"]


def test_read_status_or_success_defaults_when_missing(tmp_path):
    repo = NoteArtifactRepository(tmp_path)

    assert repo.read_status_or_success("missing") == {"status": TaskStatus.SUCCESS.value}


def test_write_status_adds_classified_error_for_failures(tmp_path):
    repo = NoteArtifactRepository(tmp_path)

    repo.write_status("task-a", TaskStatus.FAILED, "cookie expired")

    status = repo.read_status("task-a")
    assert status["status"] == TaskStatus.FAILED.value
    assert status["message"] == "cookie expired"
    assert status["error"]["category"]


def test_cache_paths_round_trip(tmp_path):
    repo = NoteArtifactRepository(tmp_path)

    repo.write_audio_cache("task-a", {"title": "audio"})
    repo.write_transcript_cache("task-a", {"full_text": "text", "segments": []})
    markdown_path = repo.write_markdown_cache("task-a", "# Note")

    assert repo.read_audio_cache("task-a") == {"title": "audio"}
    assert repo.read_transcript_cache("task-a") == {"full_text": "text", "segments": []}
    assert markdown_path.read_text(encoding="utf-8") == "# Note"


def test_delete_task_files_removes_task_artifacts_only(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    repo.write_result("task-a", {"markdown": "hello"})
    repo.write_status("task-a", TaskStatus.SUCCESS, "done")
    repo.write_transcript_cache("task-a", {"full_text": "cached", "segments": []})
    repo.write_audio_cache("task-a", {"title": "audio"})
    repo.write_markdown_cache("task-a", "# Note")
    repo.write_result("task-b", {"markdown": "keep"})
    repo.write_result("task-a-sibling", {"markdown": "keep-prefix"})

    assert repo.delete_task_files("task-a") == 5
    assert repo.read_result("task-a") is None
    assert repo.read_status("task-a") is None
    assert repo.read_transcript_cache("task-a") is None
    assert repo.read_audio_cache("task-a") is None
    assert not repo.markdown_cache_path("task-a").exists()
    assert repo.read_result("task-b") == {"markdown": "keep"}
    assert repo.read_result("task-a-sibling") == {"markdown": "keep-prefix"}
