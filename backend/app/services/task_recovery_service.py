from __future__ import annotations

from app.db.paper_task_dao import list_paper_tasks
from app.enmus.task_status_enums import TaskStatus
from app.repositories.paper_artifacts import PaperArtifactRepository


TERMINAL_STATUSES = {TaskStatus.SUCCESS.value, TaskStatus.FAILED.value}


def recover_interrupted_tasks(
    artifacts: PaperArtifactRepository | None = None,
    db_tasks: list[dict] | None = None,
) -> list[str]:
    """Fail closed for work that could not survive a process restart.

    The current executor cannot safely resume a model request. Converting
    stale in-progress states to an explicit retryable failure prevents the UI from
    polling forever and avoids silently reissuing a billable request.
    """
    injected_artifacts = artifacts is not None
    artifacts = artifacts or PaperArtifactRepository()
    if db_tasks is None:
        # Unit callers commonly inject an isolated repository. Do not couple
        # those repositories to the process-global database unless requested.
        db_tasks = [] if injected_artifacts else list_paper_tasks()

    recovered: list[str] = []
    suffix = ".status.json"
    candidates: set[str] = set()
    if artifacts.output_dir.is_dir():
        for status_path in artifacts.output_dir.glob(f"*{suffix}"):
            if status_path.name.endswith(suffix):
                candidates.add(status_path.name[:-len(suffix)])
    db_task_ids = {
        str(task.get("task_id") or "")
        for task in db_tasks
        if str(task.get("task_id") or "")
    }
    candidates.update(db_task_ids)

    for task_id in sorted(candidates):
        try:
            payload = artifacts.read_status(task_id) or {}
            status = str(payload.get("status") or "")
            if status in TERMINAL_STATUSES:
                continue
            if not status:
                # A completed result without a status file already has a safe
                # success fallback. A DB-only row is the crash window between
                # database upsert and the first status write and must not poll
                # forever as PENDING.
                if artifacts.result_exists(task_id) or task_id not in db_task_ids:
                    continue
            artifacts.write_status(
                task_id,
                TaskStatus.FAILED,
                "服务重启中断了未完成任务；为避免重复扣费，任务未自动重放，请手动重试。",
            )
            recovered.append(task_id)
        except (OSError, ValueError):
            # Ignore malformed filenames; repository containment remains authoritative.
            continue
    return recovered
