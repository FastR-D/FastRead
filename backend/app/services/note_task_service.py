from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import re
import time
import uuid
from typing import Callable, Optional, Protocol
from urllib.parse import urlparse

from app.db.video_task_dao import (
    delete_task_by_task_id,
    delete_task_by_video,
    list_task_ids_by_video,
    list_video_tasks,
    update_task_collection,
    upsert_video_task,
)
from app.core.settings import get_settings
from app.enmus.note_enums import DownloadQuality
from app.enmus.task_status_enums import TaskStatus
from app.models.task_snapshot import TaskSnapshot
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.error_classifier import classify_generation_error
from app.services.insight_extractor import build_insights
from app.services.note import NoteGenerator
from app.services.online_verifier import verify_claims_online
from app.services.task_serial_executor import task_serial_executor
from app.services.verification import claim_pipeline
from app.services.verification import fetching as verification_fetching
from app.services.verification import pipeline as verification_pipeline
from app.services.verification.schemas import utc_now_iso
from app.utils.logger import get_logger
from app.utils.url_parser import extract_video_id

logger = get_logger(__name__)


class VectorStoreLifecycle(Protocol):
    def index_task(self, task_id: str) -> None:
        ...

    def delete_index(self, task_id: str) -> None:
        ...


VectorStoreFactory = Callable[[], VectorStoreLifecycle]


class ArtifactVerificationCache:
    def __init__(self, artifacts: NoteArtifactRepository):
        self.artifacts = artifacts

    def read(self, kind: str, key: str) -> dict | None:
        return self.artifacts.read_verification_cache(kind, key)

    def write(self, kind: str, key: str, payload: dict) -> None:
        self.artifacts.write_verification_cache(kind, key, payload)


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
        deleted_upload = self._delete_owned_paper_upload(task_id)
        deleted_files = self.artifacts.delete_task_files(task_id)
        try:
            self._vector_store_factory().delete_index(task_id)
        except Exception as exc:
            logger.warning(f"删除向量索引失败（不影响任务删除）: {exc}")
        return deleted_files + deleted_upload

    def _delete_owned_paper_upload(self, task_id: str) -> int:
        """Delete only UUID-named PDFs created by the local paper upload endpoint."""
        result = self.artifacts.read_result(task_id) or {}
        paper = result.get("paper_document") or {}
        if not (result.get("paper_task") and paper):
            return 0

        settings = get_settings()
        uploads_prefix = settings.uploads_path.rstrip("/") + "/"
        raw_url = str(paper.get("pdf_url") or paper.get("source_url") or "")
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
        try:
            target.unlink()
            return 1
        except Exception as exc:
            logger.warning(f"删除论文上传文件失败 ({target}): {exc}")
            return 0

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
            stage_callback=self._verification_stage_writer(task_id),
            cache=self._verification_cache(),
            enable_geo_compare=True,
        )
        result["insights"] = insights
        self._attach_verification_artifact_refs(task_id, result)

        def merge_online_verification(latest: dict) -> dict:
            latest_insights = latest.setdefault("insights", {})
            latest_insights["verification"] = insights["verification"]
            latest["insights"] = latest_insights
            self._attach_verification_artifact_refs(task_id, latest)
            return latest

        merged = self.artifacts.update_result(task_id, merge_online_verification)
        return {"ok": True, "data": {"task_id": task_id, "insights": merged.get("insights") or {}}}

    def create_verification_task(
        self,
        *,
        text: str = "",
        url: str = "",
        source_task_id: str | None = None,
        max_claims: int = 50,
        verification_depth: str = "deep",
        source_policy: str = "authoritative",
        model_name: str | None = None,
        provider_id: str | None = None,
    ) -> dict:
        task_id = str(uuid.uuid4())
        input_payload = {
            "goal": "verify",
            "input_mode": "url" if url else "text",
            "text": text,
            "url": url,
            "source_task_id": source_task_id or "",
            "verification_depth": verification_depth or "deep",
            "source_policy": source_policy or "authoritative",
            "max_claims": max(1, min(int(max_claims or 50), 50)),
            "model_name": model_name or "",
            "provider_id": provider_id or "",
        }
        self.update_status(task_id, TaskStatus.EXTRACTING_CLAIMS, "解析输入并提取可核验主张")
        result = {
            "verification_task": True,
            "markdown": "",
            "transcript": {"full_text": text or "", "segments": [], "language": "zh"},
            "audio_meta": {"title": "联网核实任务", "platform": "verification", "raw_info": {"url": url}},
            "verification_input": input_payload,
            "insights": {
                "version": 2,
                "cards": [],
                "scores": {},
                "verification": self._build_verification_seed(
                    text=text,
                    url=url,
                    max_claims=input_payload["max_claims"],
                ),
            },
        }
        self.artifacts.write_result(task_id, result)
        return {"task_id": task_id, "status": TaskStatus.EXTRACTING_CLAIMS.value, "input": input_payload}

    def execute_verification_task(
        self,
        task_id: str,
        retry_failed_only: bool = False,
        rerun_claim_ids: set[str] | None = None,
        rerun_claim_texts: set[str] | None = None,
    ) -> None:
        result = self.artifacts.read_result(task_id)
        if not result:
            self.update_status(task_id, TaskStatus.FAILED, "核验任务不存在")
            return
        input_payload = result.get("verification_input") or {}
        rerun_claim_ids = set(rerun_claim_ids or set())
        rerun_claim_texts = {str(text) for text in (rerun_claim_texts or set()) if str(text)}
        input_source_audit = None
        rebuild_seed_from_fetched_body = False
        try:
            text = input_payload.get("text") or ""
            url = input_payload.get("url") or ""
            if url and not text:
                self.update_status(task_id, TaskStatus.FETCHING_SOURCES, "抓取待核实页面正文")
                snapshot = verification_fetching.fetch_source_snapshot(url, {"title": url})
                input_source_audit = self._input_source_audit(url, snapshot)
                text = snapshot.get("text") or url
                result["transcript"] = {"full_text": text, "segments": [], "language": "zh"}
                if snapshot.get("text"):
                    rebuild_seed_from_fetched_body = True
                    audio_meta = result.setdefault("audio_meta", {})
                    audio_meta["title"] = snapshot.get("title") or audio_meta.get("title") or "联网核实任务"
                    raw_info = audio_meta.setdefault("raw_info", {})
                    raw_info.update({
                        "url": snapshot.get("url") or url,
                        "authors": snapshot.get("authors") or ([snapshot.get("author")] if snapshot.get("author") else []),
                        "published_at": snapshot.get("published_at") or "",
                        "venue": snapshot.get("venue") or "",
                        "doi": snapshot.get("doi") or "",
                        "page_spans": snapshot.get("page_spans") or [],
                    })

            if input_payload.get("source_task_id"):
                source_result = self.artifacts.read_result(input_payload["source_task_id"])
                if source_result:
                    text = self.build_verification_context(source_result)
                    result["source_result"] = {"task_id": input_payload["source_task_id"]}

            self.update_status(task_id, TaskStatus.SEARCHING_WEB, "多策略联网检索")
            insights = result.setdefault("insights", {})
            verification = (
                self._build_verification_seed(
                    text=text,
                    url="",
                    max_claims=input_payload.get("max_claims", 50),
                )
                if rebuild_seed_from_fetched_body
                else insights.get("verification") or self._build_verification_seed(
                    text=text,
                    url=url,
                    max_claims=input_payload.get("max_claims", 50),
                )
            )
            reusable_results = (
                self._reusable_verification_claim_results(
                    task_id,
                    verification,
                    max_claims=input_payload.get("max_claims", 50),
                    exclude_claim_ids=rerun_claim_ids,
                    exclude_claim_texts=rerun_claim_texts,
                )
                if retry_failed_only
                else {}
            )
            insights["verification"] = verify_claims_online(
                verification,
                max_claims=input_payload.get("max_claims", 50),
                model_name=input_payload.get("model_name") or None,
                provider_id=input_payload.get("provider_id") or None,
                context=text,
                stage_callback=self._verification_stage_writer(task_id),
                reuse_claim_results=reusable_results,
                cache=self._verification_cache(),
                enable_geo_compare=(input_payload.get("verification_depth") or "deep") == "deep",
            )
            self.update_status(task_id, TaskStatus.WRITING_REPORT, "写入可审计核验报告")
            result["insights"] = insights
            result["verification_result"] = insights["verification"].get("result")
            if input_source_audit and result["verification_result"]:
                result["verification_result"].setdefault("audit", {})["input_source"] = input_source_audit
            self._attach_verification_artifact_refs(task_id, result)

            def merge_verification_task(latest: dict) -> dict:
                if rebuild_seed_from_fetched_body:
                    latest["transcript"] = result.get("transcript") or latest.get("transcript") or {}
                    latest_audio = latest.setdefault("audio_meta", {})
                    result_audio = result.get("audio_meta") or {}
                    if result_audio.get("title"):
                        latest_audio["title"] = result_audio["title"]
                    latest_raw = latest_audio.setdefault("raw_info", {})
                    latest_raw.update(result_audio.get("raw_info") or {})
                    latest["audio_meta"] = latest_audio
                if result.get("source_result"):
                    latest["source_result"] = result["source_result"]
                latest_insights = latest.setdefault("insights", {})
                latest_insights["verification"] = insights["verification"]
                latest["insights"] = latest_insights
                latest["verification_result"] = result.get("verification_result")
                latest.pop("verification_error", None)
                self._attach_verification_artifact_refs(task_id, latest)
                return latest

            self.artifacts.update_result(task_id, merge_verification_task)
            self.update_status(task_id, TaskStatus.SUCCESS, "联网核实完成")
        except Exception as exc:
            logger.error(f"联网核实任务失败 (task_id={task_id}): {exc}", exc_info=True)
            self.artifacts.update_result(
                task_id,
                lambda latest: {**latest, "verification_error": str(exc)},
            )
            self.update_status(task_id, TaskStatus.FAILED, f"联网核实失败: {exc}")

    def rerun_verification_task(self, task_id: str, retry_failed_only: bool = True) -> dict:
        if not self.artifacts.read_result(task_id):
            return {"ok": False, "code": 404, "message": "核验任务不存在"}
        self.execute_verification_task(task_id, retry_failed_only=retry_failed_only)
        return {"ok": True, "data": self.get_verification_task(task_id)}

    def rerun_verification_claim(self, task_id: str, claim_id: str) -> dict:
        result = self.artifacts.read_result(task_id)
        if not result:
            return {"ok": False, "code": 404, "message": "核验任务不存在"}

        input_payload = result.get("verification_input") or {}
        verification = ((result.get("insights") or {}).get("verification") or {})
        target_claim_text = self._verification_claim_text_for_id(
            task_id,
            verification,
            claim_id,
            max_claims=input_payload.get("max_claims", 50),
        )
        if not target_claim_text:
            return {"ok": False, "code": 404, "message": "核验主张不存在"}

        self.execute_verification_task(
            task_id,
            retry_failed_only=True,
            rerun_claim_ids={claim_id},
            rerun_claim_texts={target_claim_text},
        )
        return {"ok": True, "data": self.get_verification_task(task_id)}

    def get_verification_task(self, task_id: str) -> dict:
        return self.get_task_status(task_id)

    def list_verification_tasks(self) -> list[dict]:
        tasks = []
        if not self.artifacts.output_dir_exists():
            return tasks
        for result_file in self.artifacts.iter_result_files():
            result = self.artifacts.read_result(result_file.task_id)
            if not result or not result.get("verification_task"):
                continue
            tasks.append(self._build_file_task_snapshot(result_file.task_id, result, result_file.modified_at).to_list_payload())
        tasks.sort(key=lambda item: item.get("updatedAt") or item.get("createdAt") or 0, reverse=True)
        return tasks

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

    def _verification_stage_writer(self, task_id: str):
        def _write(event: dict) -> None:
            self._write_verification_stage(task_id, event)

        return _write

    def _verification_cache(self) -> ArtifactVerificationCache:
        return ArtifactVerificationCache(self.artifacts)

    @staticmethod
    def _input_source_audit(original_url: str, snapshot: dict) -> dict:
        text = snapshot.get("text") or ""
        return {
            "input_mode": "url",
            "requested_url": original_url,
            "fetched_url": snapshot.get("url") or original_url,
            "canonical_url": snapshot.get("canonical_url") or "",
            "title": snapshot.get("title") or "",
            "publisher": snapshot.get("publisher") or "",
            "author": snapshot.get("author") or "",
            "published_at": snapshot.get("published_at") or "",
            "retrieved_at": snapshot.get("retrieved_at") or "",
            "fetch_status": snapshot.get("fetch_status") or "",
            "source_type": snapshot.get("source_type") or "",
            "redirect_chain": snapshot.get("redirect_chain") or [],
            "text_chars": len(text),
            "error": snapshot.get("error") or "",
        }

    def _write_verification_stage(self, task_id: str, event: dict) -> None:
        claim_id = event.get("claim_id")
        if not claim_id:
            return

        now = utc_now_iso()
        artifact = self.artifacts.read_verification_claim_artifact(task_id, claim_id) or {
            "task_id": task_id,
            "claim_id": claim_id,
            "created_at": now,
            "stages": [],
            "fetches": [],
        }
        artifact["updated_at"] = now

        stage = event.get("stage") or "unknown"
        artifact["stages"].append({
            "stage": stage,
            "recorded_at": now,
            "raw_result_count": event.get("raw_result_count"),
            "fetch_status": event.get("fetch_status"),
            "evidence_added": event.get("evidence_added"),
            "search_error": event.get("search_error"),
            "cache_hit": event.get("cache_hit"),
            "cache_key": event.get("cache_key"),
        })

        if stage == "claim_started":
            artifact.update({
                "status": "running",
                "atomic_claim": event.get("atomic_claim") or "",
                "claim_facts": event.get("claim_facts") or {},
                "queries": event.get("queries") or [],
                "context_chars": event.get("context_chars", 0),
            })
        elif stage == "search_completed":
            artifact["status"] = "search_completed" if not event.get("search_error") else "search_failed"
            artifact["search"] = {
                "queries": event.get("queries") or [],
                "search_providers": event.get("search_providers") or [],
                "raw_result_count": event.get("raw_result_count", 0),
                "search_error": event.get("search_error") or "",
                "raw_results": event.get("raw_results") or [],
                "cache_hit": bool(event.get("cache_hit")),
                "cache_key": event.get("cache_key") or "",
            }
        elif stage == "source_fetched":
            source = event.get("source") or {}
            artifact["fetches"].append({
                "url": event.get("url") or source.get("url") or "",
                "canonical_url": source.get("canonical_url") or "",
                "domain": source.get("domain") or "",
                "trust_tier": source.get("trust_tier") or "",
                "fetch_status": event.get("fetch_status") or source.get("fetch_status") or "",
                "content_hash": event.get("content_hash") or source.get("content_hash") or "",
                "evidence_added": event.get("evidence_added", 0),
                "snapshot_cache_hit": bool(event.get("cache_hit")),
                "snapshot_cache_key": event.get("cache_key") or "",
                "evidence_cache_hit": bool(event.get("evidence_cache_hit")),
                "evidence_cache_key": event.get("evidence_cache_key") or "",
                "recorded_at": now,
            })
            artifact["status"] = "fetching_sources"
        elif stage == "claim_completed":
            claim_result = event.get("result") or {}
            source_ids = [source.get("source_id") for source in claim_result.get("sources", []) if source.get("source_id")]
            evidence_ids = [
                item.get("evidence_id")
                for item in claim_result.get("evidence", [])
                if item.get("evidence_id")
            ]
            artifact["status"] = "completed"
            artifact["verdict"] = claim_result.get("verdict") or ""
            artifact["confidence"] = claim_result.get("confidence", 0)
            artifact["risk_flags"] = claim_result.get("risk_flags") or []
            artifact["audit_ids"] = {
                "claim_id": claim_result.get("claim_id") or claim_id,
                "source_ids": source_ids,
                "evidence_ids": evidence_ids,
            }
            artifact["result"] = claim_result

        self.artifacts.write_verification_claim_artifact(task_id, claim_id, artifact)

    def _reusable_verification_claim_results(
        self,
        task_id: str,
        verification: dict,
        max_claims: int = 50,
        exclude_claim_ids: set[str] | None = None,
        exclude_claim_texts: set[str] | None = None,
    ) -> dict[str, dict]:
        reusable = {}
        exclude_claim_ids = set(exclude_claim_ids or set())
        exclude_claim_texts = {str(text) for text in (exclude_claim_texts or set()) if str(text)}
        selected = claim_pipeline.sort_claims_by_verification_risk(
            list(verification.get("claims") or []),
            max(1, min(int(max_claims or 50), 50)),
        )
        for index, claim in enumerate(selected):
            claim_text = claim.get("claim") or claim.get("text") or ""
            if not claim_text:
                continue
            if claim_text in exclude_claim_texts:
                continue
            candidate_ids = self._verification_claim_candidate_ids(claim, claim_text, index)
            if any(candidate_id in exclude_claim_ids for candidate_id in candidate_ids):
                continue
            artifact = self._completed_claim_artifact_for_candidates(task_id, claim_text, candidate_ids)
            if artifact.get("status") != "completed":
                continue
            result = artifact.get("result") or {}
            if not result:
                continue
            reusable[claim_text] = result
        return reusable

    def _verification_claim_candidate_ids(self, claim: dict, claim_text: str, index: int) -> list[str]:
        candidates = [
            ((claim.get("online") or {}).get("claim_id") or ""),
            claim.get("claim_id") or "",
            verification_pipeline.claim_id_for(claim_text, index),
        ]
        ordered = []
        for candidate in candidates:
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    def _completed_claim_artifact_for_candidates(
        self,
        task_id: str,
        claim_text: str,
        candidate_ids: list[str],
    ) -> dict:
        for candidate_id in candidate_ids:
            artifact = self.artifacts.read_verification_claim_artifact(task_id, candidate_id) or {}
            if artifact.get("status") != "completed":
                continue
            artifact_claim = artifact.get("atomic_claim") or (artifact.get("result") or {}).get("atomic_claim") or ""
            if artifact_claim and artifact_claim != claim_text:
                continue
            return artifact
        return {}

    def _verification_claim_text_for_id(
        self,
        task_id: str,
        verification: dict,
        claim_id: str,
        max_claims: int = 50,
    ) -> str:
        selected = claim_pipeline.sort_claims_by_verification_risk(
            list(verification.get("claims") or []),
            max(1, min(int(max_claims or 50), 50)),
        )
        artifact = self.artifacts.read_verification_claim_artifact(task_id, claim_id) or {}
        artifact_claim = artifact.get("atomic_claim") or (artifact.get("result") or {}).get("atomic_claim") or ""
        for index, claim in enumerate(selected):
            claim_text = claim.get("claim") or claim.get("text") or ""
            if not claim_text:
                continue
            if claim_id in self._verification_claim_candidate_ids(claim, claim_text, index):
                return claim_text
            if artifact_claim and artifact_claim == claim_text:
                return claim_text
        return ""

    def _verification_has_claim_id(self, verification: dict, claim_id: str, max_claims: int = 50) -> bool:
        selected = claim_pipeline.sort_claims_by_verification_risk(
            list(verification.get("claims") or []),
            max(1, min(int(max_claims or 50), 50)),
        )
        for index, claim in enumerate(selected):
            claim_text = claim.get("claim") or claim.get("text") or ""
            if claim_text and verification_pipeline.claim_id_for(claim_text, index) == claim_id:
                return True
        return False

    def _attach_verification_artifact_refs(self, task_id: str, result: dict) -> None:
        verification = (result.get("insights") or {}).get("verification") or {}
        claims = verification.get("claims") or []
        for claim in claims:
            online = claim.get("online") or {}
            claim_id = online.get("claim_id")
            if not claim_id:
                continue
            artifact_path = str(self.artifacts.verification_claim_path(task_id, claim_id))
            online["claim_artifact_path"] = artifact_path
            audit = online.setdefault("audit", {})
            audit["claim_artifact_path"] = artifact_path
            claim["online"] = online

        report = verification.get("result") or result.get("verification_result") or {}
        if report:
            report.setdefault("audit", {})["artifact_root"] = str(self.artifacts.verification_task_dir(task_id))
            result["verification_result"] = report

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
        if result.get("insights") and any(
            result["insights"].get(key)
            for key in ("verification", "reading_report", "academic_gate")
        ):
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

    def _build_verification_seed(self, *, text: str, url: str = "", max_claims: int = 50) -> dict:
        atomic_claims = claim_pipeline.split_atomic_claims(text or url, max_claims=max_claims)
        claims = []
        for index, claim_text in enumerate(atomic_claims):
            facts = claim_pipeline.extract_claim_facts(claim_text)
            risk_level = "high" if facts.risk_topics else "medium"
            claims.append({
                "claim": claim_text,
                "type": facts.domain_type,
                "type_label": facts.domain_type,
                "risk_level": risk_level,
                "risk_topics": facts.risk_topics,
                "verdict": "等待联网核实",
                "confidence": 0,
                "reason": "已提取主张，等待联网检索、正文抓取和交叉判定。",
                "evidence_hint": "",
                "priority": 100 - index,
            })
        return {
            "version": 2,
            "external_check": False,
            "overall": {
                "status": "等待联网核实",
                "score": 0,
                "summary": f"已提取 {len(claims)} 条可核验主张。",
                "note": "搜索摘要只作为召回线索；最终结论必须来自正文证据、信源分级和独立性交叉判定。",
            },
            "claim_counts": {
                "total": len(claims),
                "needs_review": len(claims),
                "high_risk": sum(1 for claim in claims if claim["risk_level"] == "high"),
                "medium_risk": sum(1 for claim in claims if claim["risk_level"] == "medium"),
            },
            "claims": claims,
            "sources": [],
            "evidence": [],
            "risk_flags": [],
        }

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
