from app.enmus.task_status_enums import TaskStatus
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.note_lifecycle_service import NoteLifecycleService


class DetailError(Exception):
    def __init__(self, detail):
        super().__init__("fallback")
        self.detail = detail


def test_update_status_ignores_missing_task_id(tmp_path):
    service = NoteLifecycleService(NoteArtifactRepository(tmp_path))

    service.update_status(None, TaskStatus.PARSING)

    assert list(tmp_path.iterdir()) == []


def test_handle_exception_serializes_detail_dict(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteLifecycleService(repo)

    service.handle_exception("task-a", DetailError({"reason": "bad"}))

    status = repo.read_status("task-a")
    assert status["status"] == TaskStatus.FAILED.value
    assert status["message"] == '{"reason": "bad"}'


def test_save_metadata_delegates_to_video_task_dao(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("app.services.note_lifecycle_service.upsert_video_task", lambda **kwargs: calls.append(kwargs))
    service = NoteLifecycleService(NoteArtifactRepository(tmp_path))

    service.save_metadata(
        video_id="video-a",
        platform="bilibili",
        task_id="task-a",
        title="Title",
        cover_url="cover",
    )

    assert calls == [{
        "video_id": "video-a",
        "platform": "bilibili",
        "task_id": "task-a",
        "title": "Title",
        "cover_url": "cover",
    }]


def test_delete_note_delegates_to_video_task_dao(monkeypatch):
    monkeypatch.setattr("app.services.note_lifecycle_service.delete_task_by_video", lambda video_id, platform: 3)

    assert NoteLifecycleService.delete_note("video-a", "douyin") == 3
