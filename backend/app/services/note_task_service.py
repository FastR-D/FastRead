from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import time
from typing import Callable, Optional, Protocol

from app.db.video_task_dao import (
    delete_task_by_task_id,
    delete_task_by_video,
    list_task_ids_by_video,
    list_video_tasks,
    update_task_collection,
    upsert_video_task,
)
from app.enmus.note_enums import DownloadQuality
from app.enmus.task_status_enums import TaskStatus
from app.models.task_snapshot import TaskSnapshot
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.error_classifier import classify_generation_error
from app.services.insight_extractor import build_insights
from app.services.note import NoteGenerator
from app.services.online_verifier import verify_claims_online
from app.services.task_serial_executor import task_serial_executor
from app.utils.logger import get_logger
from app.utils.url_parser import extract_video_id

logger = get_logger(__name__)


class VectorStoreLifecycle(Protocol):
    def index_task(self, task_id: str) -> None:
        ...

    def delete_index(self, task_id: str) -> None:
        ...


VectorStoreFactory = Callable[[], VectorStoreLifecycle]


def _default_vector_store_factory() -> VectorStoreLifecycle:
    from app.services.vector_store import VectorStoreManager

    return VectorStoreManager()


class NoteTaskService:
    """Application service for note task lifecycle operations."""

    def __init__(
        self,
        artifacts: NoteArtifactRepository | None = None,
        vector_store_factory: VectorStoreFactory | None = None,
    ):
        self.artifacts = artifacts or NoteArtifactRepository()
        self._vector_store_factory = vector_store_factory or _default_vector_store_factory

    def update_status(
        self,
        task_id: Optional[str],
        status: str | TaskStatus,
        message: Optional[str] = None,
    ) -> None:
        if task_id:
            self.artifacts.write_status(task_id, status, message=message)

    def prepare_generation_task(
        self,
        *,
        video_url: str,
        platform: str,
        task_id: str,
        collection_folder: Optional[str] = None,
        collection_tags=None,
        collection_note: Optional[str] = None,
        prefetched_transcript: Optional[dict] = None,
    ) -> str:
        video_id = extract_video_id(video_url, platform)
        upsert_video_task(
            video_id=video_id or "",
            platform=platform,
            task_id=task_id,
            video_url=video_url,
            collection_folder=collection_folder or "默认收藏夹",
            collection_tags=self.parse_collection_tags(collection_tags),
            collection_note=collection_note or "",
        )
        self.update_status(task_id, TaskStatus.PENDING)

        if prefetched_transcript:
            try:
                self.persist_prefetched_transcript(task_id, prefetched_transcript)
            except Exception as exc:
                logger.warning(f"写入预取字幕失败 (task_id={task_id}): {exc}")
        return task_id

    def execute_generation_task(
        self,
        *,
        task_id: str,
        video_url: str,
        platform: str,
        quality: DownloadQuality,
        link: bool = False,
        screenshot: bool = False,
        model_name: str | None = None,
        provider_id: str | None = None,
        formats: list | None = None,
        style: str | None = None,
        extras: str | None = None,
        video_understanding: bool = False,
        video_interval: int = 0,
        grid_size: list | None = None,
    ) -> None:
        def _execute_note_task():
            return NoteGenerator().generate(
                video_url=video_url,
                platform=platform,
                quality=quality,
                task_id=task_id,
                model_name=model_name,
                provider_id=provider_id,
                link=link,
                _format=formats,
                style=style,
                extras=extras,
                screenshot=screenshot,
                video_understanding=video_understanding,
                video_interval=video_interval,
                grid_size=grid_size or [],
            )

        logger.info(f"任务进入执行队列 (task_id={task_id})")
        note = task_serial_executor.run(_execute_note_task)
        logger.info(f"Note generated: {task_id}")
        if not note or not note.markdown:
            logger.warning(f"任务 {task_id} 执行失败，跳过保存")
            return

        self.artifacts.write_result(task_id, asdict(note))
        self.index_task(task_id)

    def delete_task(self, *, task_id: str | None = None, video_id: str | None = None, platform: str = "douyin") -> int:
        deleted = 0
        if task_id:
            deleted += delete_task_by_task_id(task_id)
            self.delete_task_artifacts(task_id)
            return deleted

        if video_id:
            task_ids = list_task_ids_by_video(video_id, platform)
            deleted += delete_task_by_video(video_id, platform)
            for item_task_id in task_ids:
                self.delete_task_artifacts(item_task_id)
        return deleted

    def delete_task_artifacts(self, task_id: str) -> int:
        deleted_files = self.artifacts.delete_task_files(task_id)
        try:
            self._vector_store_factory().delete_index(task_id)
        except Exception as exc:
            logger.warning(f"删除向量索引失败（不影响任务删除）: {exc}")
        return deleted_files

    def update_collection(
        self,
        *,
        task_id: str,
        collection_folder: Optional[str] = None,
        collection_tags=None,
        collection_note: Optional[str] = None,
    ) -> Optional[dict]:
        updated = update_task_collection(
            task_id=task_id,
            collection_folder=collection_folder,
            collection_tags=self.parse_collection_tags(collection_tags),
            collection_note=collection_note,
        )
        if not updated:
            return None
        return {
            "task_id": task_id,
            "collection": {
                "folder": updated.get("collection_folder") or "默认收藏夹",
                "tags": self.parse_collection_tags(updated.get("collection_tags")),
                "note": updated.get("collection_note") or "",
            },
        }

    def verify_task_online(
        self,
        *,
        task_id: str,
        max_claims: int = 8,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> dict:
        result = self.artifacts.read_result(task_id)
        if not result:
            return {"ok": False, "code": 404, "message": "任务结果不存在"}

        result = self.attach_note_insights(result)
        insights = result.get("insights") or {}
        verification = insights.get("verification")
        if not verification:
            return {"ok": False, "code": 400, "message": "当前任务没有可核验的主张"}

        capped_claims = max(1, min(int(max_claims or 8), 20))
        insights["verification"] = verify_claims_online(
            verification,
            max_claims=capped_claims,
            model_name=model_name,
            provider_id=provider_id,
            context=self.build_verification_context(result),
        )
        result["insights"] = insights
        self.artifacts.write_result(task_id, result)
        return {"ok": True, "data": {"task_id": task_id, "insights": insights}}

    def list_tasks(self) -> list[dict]:
        db_tasks = list_video_tasks()
        if not self.artifacts.output_dir_exists() and not db_tasks:
            return []

        snapshots = []
        seen_task_ids = set()
        for db_task in db_tasks:
            task_id = db_task["task_id"]
            seen_task_ids.add(task_id)
            result = self.artifacts.read_result(task_id) or {}
            snapshots.append(self._build_db_task_snapshot(db_task, result))

        if self.artifacts.output_dir_exists():
            for result_file in self.artifacts.iter_result_files():
                task_id = result_file.task_id
                if task_id in seen_task_ids:
                    continue
                result = self.artifacts.read_result(task_id)
                if result:
                    snapshots.append(self._build_file_task_snapshot(task_id, result, result_file.modified_at))

        snapshots.sort(key=lambda item: item.created_at, reverse=True)
        return [snapshot.to_list_payload() for snapshot in snapshots]

    def get_task_status(self, task_id: str) -> dict:
        status_content = self.artifacts.read_status(task_id)
        if status_content:
            return self._snapshot_from_status_file(task_id, status_content).to_status_payload()

        result_content = self.artifacts.read_result(task_id)
        if result_content:
            return self._snapshot_from_result(task_id, result_content).to_status_payload()

        return TaskSnapshot(
            id=task_id,
            status=TaskStatus.PENDING.value,
            message="任务排队中",
        ).to_status_payload()

    def index_task(self, task_id: str) -> None:
        try:
            self._vector_store_factory().index_task(task_id)
        except Exception as exc:
            logger.warning(f"向量索引失败（不影响笔记）: {exc}")

    def persist_prefetched_transcript(self, task_id: str, transcript: dict) -> None:
        segments = transcript.get("segments") or []
        cleaned_segments = []
        for segment in segments:
            text = (segment.get("text") or "").strip()
            if not text:
                continue
            cleaned_segments.append({
                "start": float(segment.get("start", 0)),
                "end": float(segment.get("end", 0)),
                "text": text,
            })
        if not cleaned_segments:
            raise ValueError("prefetched_transcript 没有可用的 segments")

        full_text = transcript.get("full_text") or " ".join(segment["text"] for segment in cleaned_segments)
        payload = {
            "language": transcript.get("language") or "zh",
            "full_text": full_text,
            "segments": cleaned_segments,
        }
        target = self.artifacts.write_transcript_cache(task_id, payload)
        logger.info(f"已写入客户端预取字幕缓存: {target} ({len(cleaned_segments)} 段)")

    def attach_note_insights(self, result: dict) -> dict:
        insights = self.get_note_insights(result)
        if insights:
            result["insights"] = insights
        return result

    def get_note_insights(self, result: dict) -> Optional[dict]:
        if result.get("insights") and result["insights"].get("verification"):
            return result.get("insights")

        markdown = result.get("markdown") or ""
        transcript = result.get("transcript") or {}
        audio_meta = result.get("audio_meta") or {}
        if not markdown and not transcript and not audio_meta:
            return None
        try:
            return build_insights(markdown, transcript, audio_meta)
        except Exception as exc:
            logger.warning(f"生成历史笔记洞察失败: {exc}")
            return None

    @staticmethod
    def parse_collection_tags(raw) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(tag).strip() for tag in raw if str(tag).strip()]
        return [tag.strip() for tag in str(raw).replace("，", ",").split(",") if tag.strip()]

    @staticmethod
    def extract_source_url(markdown: str) -> str:
        if not markdown:
            return ""
        first_line = markdown.splitlines()[0] if markdown.splitlines() else ""
        prefix = "> 来源链接："
        return first_line.replace(prefix, "").strip() if first_line.startswith(prefix) else ""

    @staticmethod
    def created_at_to_timestamp(value) -> float:
        if not value:
            return 0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return float(time.mktime(value.timetuple()) + value.microsecond / 1_000_000)
            return value.timestamp()
        try:
            return value.timestamp()
        except Exception:
            return 0

    @staticmethod
    def build_verification_context(result: dict) -> str:
        audio_meta = result.get("audio_meta") or {}
        transcript = result.get("transcript") or {}
        raw_info = audio_meta.get("raw_info") or {}
        parts = [
            f"标题：{audio_meta.get('title') or raw_info.get('title') or ''}",
            f"平台：{audio_meta.get('platform') or ''}",
            f"标签：{raw_info.get('tags') or raw_info.get('hashtags') or ''}",
            f"视频简介：{raw_info.get('desc') or raw_info.get('caption') or ''}",
            f"笔记内容：{result.get('markdown') or ''}",
            f"转录全文：{transcript.get('full_text') or ''}",
        ]
        return "\n\n".join(str(part) for part in parts if str(part).strip())

    def _build_db_task_snapshot(self, db_task: dict, result: dict) -> TaskSnapshot:
        task_id = db_task["task_id"]
        markdown = result.get("markdown") or ""
        audio_meta = result.get("audio_meta") or {}
        transcript = result.get("transcript")
        status_payload = self.artifacts.read_status_or_success(task_id)
        created_at = self.created_at_to_timestamp(db_task.get("created_at"))
        updated_at = self.created_at_to_timestamp(db_task.get("updated_at")) or created_at
        result_payload = self.attach_note_insights(result) if result else None
        return TaskSnapshot(
            id=task_id,
            status=status_payload.get("status"),
            message=status_payload.get("message", ""),
            error=status_payload.get("error"),
            result=result_payload,
            markdown=markdown,
            insights=self.get_note_insights(result),
            audio_meta=audio_meta,
            transcript=transcript,
            created_at=created_at,
            updated_at=updated_at,
            video_url=db_task.get("video_url") or self.extract_source_url(markdown),
            collection={
                "folder": db_task.get("collection_folder") or "默认收藏夹",
                "tags": self.parse_collection_tags(db_task.get("collection_tags")),
                "note": db_task.get("collection_note") or "",
            },
            title=db_task.get("title") or audio_meta.get("title") or "",
            cover_url=db_task.get("cover_url") or audio_meta.get("cover_url") or "",
        )

    def _build_file_task_snapshot(self, task_id: str, result: dict, modified_at: float) -> TaskSnapshot:
        markdown = result.get("markdown") or ""
        audio_meta = result.get("audio_meta") or {}
        transcript = result.get("transcript")
        status_payload = self.artifacts.read_status_or_success(task_id)
        result_payload = self.attach_note_insights(result) if result else None
        return TaskSnapshot(
            id=task_id,
            status=status_payload.get("status"),
            message=status_payload.get("message", ""),
            error=status_payload.get("error"),
            result=result_payload,
            markdown=markdown,
            insights=self.get_note_insights(result),
            audio_meta=audio_meta,
            transcript=transcript,
            created_at=modified_at,
            updated_at=modified_at,
            video_url=self.extract_source_url(markdown),
            title=audio_meta.get("title") or "",
            cover_url=audio_meta.get("cover_url") or "",
        )

    def _snapshot_from_result(self, task_id: str, result_content: dict, message: str = "") -> TaskSnapshot:
        result = self.attach_note_insights(result_content)
        return TaskSnapshot(
            id=task_id,
            status=TaskStatus.SUCCESS.value,
            message=message,
            result=result,
            markdown=result.get("markdown") or "",
            insights=result.get("insights"),
            audio_meta=result.get("audio_meta") or {},
            transcript=result.get("transcript"),
            video_url=self.extract_source_url(result.get("markdown") or ""),
            title=(result.get("audio_meta") or {}).get("title") or "",
            cover_url=(result.get("audio_meta") or {}).get("cover_url") or "",
        )

    def _snapshot_from_status_file(self, task_id: str, status_content: dict) -> TaskSnapshot:
        status = status_content.get("status")
        message = status_content.get("message", "")

        if status == TaskStatus.SUCCESS.value:
            result_content = self.artifacts.read_result(task_id)
            if result_content:
                return self._snapshot_from_result(task_id, result_content, message=message)
            return TaskSnapshot(
                id=task_id,
                status=TaskStatus.PENDING.value,
                message="任务完成，但结果文件未找到",
            )

        if status == TaskStatus.FAILED.value:
            return TaskSnapshot(
                id=task_id,
                status=status,
                message=message,
                error=status_content.get("error") or classify_generation_error(message),
            )

        return TaskSnapshot(
            id=task_id,
            status=status,
            message=message,
        )
