from __future__ import annotations

import json
from typing import Optional

from app.db.video_task_dao import delete_task_by_video, upsert_video_task
from app.enmus.task_status_enums import TaskStatus
from app.repositories.note_artifacts import NoteArtifactRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NoteLifecycleService:
    """Status and persistence side effects for note generation."""

    def __init__(self, artifacts: NoteArtifactRepository):
        self.artifacts = artifacts

    def update_status(
        self,
        task_id: Optional[str],
        status: str | TaskStatus,
        message: Optional[str] = None,
    ) -> None:
        if task_id:
            self.artifacts.write_status(task_id, status, message=message)

    def handle_exception(self, task_id: Optional[str], exc: Exception) -> None:
        logger.error(f"任务异常 (task_id={task_id})", exc_info=True)
        self.update_status(task_id, TaskStatus.FAILED, message=self.format_error_message(exc))

    def save_metadata(
        self,
        *,
        video_id: str,
        platform: str,
        task_id: str,
        title: str | None = None,
        cover_url: str | None = None,
    ) -> None:
        try:
            upsert_video_task(
                video_id=video_id,
                platform=platform,
                task_id=task_id,
                title=title,
                cover_url=cover_url,
            )
            logger.info(f"已保存任务记录到数据库 (video_id={video_id}, platform={platform}, task_id={task_id})")
        except Exception as exc:
            logger.error(f"保存任务记录失败：{exc}")

    @staticmethod
    def delete_note(video_id: str, platform: str) -> int:
        logger.info(f"删除笔记记录 (video_id={video_id}, platform={platform})")
        return delete_task_by_video(video_id, platform)

    @staticmethod
    def format_error_message(exc: Exception) -> str:
        error_message = getattr(exc, "detail", str(exc))
        if isinstance(error_message, dict):
            try:
                return json.dumps(error_message, ensure_ascii=False)
            except Exception:
                return str(error_message)
        return str(error_message)
