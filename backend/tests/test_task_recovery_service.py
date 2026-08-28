from app.enmus.task_status_enums import TaskStatus
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.task_recovery_service import recover_interrupted_tasks


def test_recovery_marks_incomplete_tasks_failed_without_replaying(tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_status("task-a", TaskStatus.WRITING_REPORT, "writing")
    artifacts.write_status("task-b", TaskStatus.SUCCESS, "done")

    recovered = recover_interrupted_tasks(artifacts)

    assert recovered == ["task-a"]
    assert artifacts.read_status("task-a")["status"] == TaskStatus.FAILED.value
    assert "未自动重放" in artifacts.read_status("task-a")["message"]
    assert artifacts.read_status("task-b")["status"] == TaskStatus.SUCCESS.value


def test_recovery_marks_db_only_task_failed(tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)

    recovered = recover_interrupted_tasks(
        artifacts,
        db_tasks=[{"task_id": "task-db-only"}],
    )

    assert recovered == ["task-db-only"]
    assert artifacts.read_status("task-db-only")["status"] == TaskStatus.FAILED.value


def test_recovery_does_not_report_status_write_failure(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_status("task-a", TaskStatus.WRITING_REPORT, "writing")
    def fail_write(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(artifacts, "write_status", fail_write)

    recovered = recover_interrupted_tasks(artifacts)

    assert recovered == []
    assert artifacts.read_status("task-a")["status"] == TaskStatus.WRITING_REPORT.value
