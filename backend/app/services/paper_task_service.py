from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.core.settings import get_settings
from app.db.evidence_dao import EvidenceHubDAO
from app.db.paper_task_dao import (
    delete_paper_task,
    get_paper_task,
    list_paper_tasks,
    update_paper_collection,
)
from app.enmus.task_status_enums import TaskStatus
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.vector_store import VectorStoreManager
from app.utils.logger import get_logger


logger = get_logger(__name__)


def _timestamp(value) -> float:
    if value is None:
        return 0
    if isinstance(value, datetime):
        current = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return current.timestamp()
    return 0


class PaperTaskService:
    def __init__(
        self,
        artifacts: PaperArtifactRepository | None = None,
        vector_store_factory=None,
    ):
        self.artifacts = artifacts or PaperArtifactRepository()
        self._vector_store_factory = vector_store_factory or VectorStoreManager

    def _payload(self, metadata: dict, result: dict | None = None) -> dict:
        result = result or self.artifacts.read_result(metadata["task_id"]) or {}
        status = self.artifacts.read_status_or_success(metadata["task_id"])
        collection = {
            "folder": metadata.get("collection_folder") or "默认收藏夹",
            "tags": metadata.get("collection_tags") or [],
            "note": metadata.get("collection_note") or "",
        }
        return {
            "id": metadata["task_id"],
            "task_id": metadata["task_id"],
            "kind": "paper",
            "status": status.get("status") or TaskStatus.SUCCESS.value,
            "message": status.get("message") or "",
            "error": status.get("error"),
            "result": result,
            "paperDocument": result.get("paper_document") or {},
            "readingReport": (result.get("insights") or {}).get("reading_report"),
            "personalSummary": (result.get("insights") or {}).get("personal_summary"),
            "collection": collection,
            "title": metadata.get("title") or "未命名论文",
            "createdAt": _timestamp(metadata.get("created_at")),
            "updatedAt": _timestamp(metadata.get("updated_at")),
        }

    def list_tasks(self) -> list[dict]:
        return [self._payload(metadata) for metadata in list_paper_tasks()]

    def get_task_status(self, task_id: str) -> dict:
        metadata = get_paper_task(task_id)
        if metadata is None:
            return {
                "id": task_id,
                "task_id": task_id,
                "kind": "paper",
                "status": TaskStatus.PENDING.value,
                "message": "论文任务不存在或尚未持久化",
                "result": None,
            }
        return self._payload(metadata)

    def update_collection(
        self,
        *,
        task_id: str,
        collection_folder: str | None = None,
        collection_tags: list[str] | str | None = None,
        collection_note: str | None = None,
    ) -> dict | None:
        updated = update_paper_collection(
            task_id,
            collection_folder=collection_folder,
            collection_tags=collection_tags,
            collection_note=collection_note,
        )
        return self._payload(updated) if updated else None

    def delete_task(self, task_id: str) -> int:
        metadata = get_paper_task(task_id)
        if metadata is None:
            return 0
        self._delete_owned_upload(task_id)
        try:
            EvidenceHubDAO().cleanup_task_relations(task_id)
        except Exception as exc:
            logger.warning(f"清理论文摘录和专题关系失败: {exc}")
        self.artifacts.delete_task_files(task_id)
        try:
            self._vector_store_factory().delete_index(task_id)
        except Exception as exc:
            logger.warning(f"删除论文向量索引失败: {exc}")
        return int(delete_paper_task(task_id))

    def _delete_owned_upload(self, task_id: str) -> int:
        result = self.artifacts.read_result(task_id) or {}
        document = result.get("paper_document") or {}
        settings = get_settings()
        uploads_prefix = settings.uploads_path.rstrip("/") + "/"
        raw_url = str(document.get("pdf_url") or document.get("source_url") or "")
        parsed_path = urlparse(raw_url).path
        if not parsed_path.startswith(uploads_prefix):
            return 0
        filename = Path(parsed_path).name
        if not re.fullmatch(r"[0-9a-f]{32}\.pdf", filename, re.IGNORECASE):
            return 0
        uploads_dir = settings.uploads_dir.resolve()
        target = (uploads_dir / filename).resolve()
        if target.parent != uploads_dir or not target.is_file():
            return 0
        target.unlink()
        return 1
