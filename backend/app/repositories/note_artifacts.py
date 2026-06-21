import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Union

from app.core.settings import get_settings
from app.enmus.task_status_enums import TaskStatus
from app.services.error_classifier import classify_generation_error
from app.utils.logger import get_logger

logger = get_logger(__name__)


IGNORED_RESULT_SUFFIXES = (
    ".status.json",
    "_status.json",
    "_transcript.json",
    "_audio.json",
    "_markdown.status.json",
)
VERIFICATION_CACHE_KINDS = {"serp", "snapshot", "evidence"}


@dataclass(frozen=True)
class NoteResultFile:
    task_id: str
    path: Path
    modified_at: float


class NoteArtifactRepository:
    """Centralized filesystem access for note generation artifacts."""

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir is not None else get_settings().note_output_dir

    def ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def output_dir_exists(self) -> bool:
        return self.output_dir.exists()

    def result_path(self, task_id: str) -> Path:
        return self.output_dir / f"{task_id}.json"

    def status_path(self, task_id: str) -> Path:
        return self.output_dir / f"{task_id}.status.json"

    def transcript_cache_path(self, task_id: str) -> Path:
        return self.output_dir / f"{task_id}_transcript.json"

    def audio_cache_path(self, task_id: str) -> Path:
        return self.output_dir / f"{task_id}_audio.json"

    def markdown_cache_path(self, task_id: str) -> Path:
        return self.output_dir / f"{task_id}_markdown.md"

    def verification_task_dir(self, task_id: str) -> Path:
        return self.output_dir / "_verification" / task_id

    def verification_claim_path(self, task_id: str, claim_id: str) -> Path:
        return self.verification_task_dir(task_id) / "claims" / f"{claim_id}.json"

    def verification_cache_path(self, kind: str, key: str) -> Path:
        if kind not in VERIFICATION_CACHE_KINDS:
            raise ValueError(f"Unsupported verification cache kind: {kind}")
        safe_key = "".join(ch for ch in key if ch.isalnum() or ch in {"-", "_"})
        return self.output_dir / "_verification" / "_cache" / kind / f"{safe_key}.json"

    def result_exists(self, task_id: str) -> bool:
        return self.result_path(task_id).exists()

    def read_result(self, task_id: str) -> Optional[dict]:
        return self._read_json(self.result_path(task_id))

    def write_result(self, task_id: str, payload: dict) -> None:
        self._write_json(self.result_path(task_id), payload)

    def read_status(self, task_id: str) -> Optional[dict]:
        return self._read_json(self.status_path(task_id))

    def read_status_or_success(self, task_id: str) -> dict:
        data = self.read_status(task_id)
        if not data:
            return {"status": TaskStatus.SUCCESS.value}

        status = data.get("status") or TaskStatus.SUCCESS.value
        data["status"] = status
        if status == TaskStatus.FAILED.value and not data.get("error"):
            data["error"] = classify_generation_error(data.get("message"))
        return data

    def write_status(
        self,
        task_id: str,
        status: Union[str, TaskStatus],
        message: Optional[str] = None,
    ) -> None:
        payload = {"status": status.value if isinstance(status, TaskStatus) else status}
        if message:
            payload["message"] = message
        if payload["status"] == TaskStatus.FAILED.value:
            payload["error"] = classify_generation_error(message)

        self.ensure_output_dir()
        target = self.status_path(task_id)
        tmp_path = target.with_suffix(".tmp")
        try:
            self._write_json(tmp_path, payload)
            tmp_path.replace(target)
        except Exception as exc:
            logger.error(f"写入任务状态失败 (task_id={task_id}): {exc}")
            try:
                target.write_text(f"Error writing status: {exc}", encoding="utf-8")
            except Exception as fallback_exc:
                logger.error(f"写入任务状态兜底失败 (task_id={task_id}): {fallback_exc}")

    def read_audio_cache(self, task_id: str) -> Optional[dict]:
        return self._read_json(self.audio_cache_path(task_id))

    def write_audio_cache(self, task_id: str, payload: dict) -> Path:
        target = self.audio_cache_path(task_id)
        self._write_json(target, payload)
        return target

    def read_transcript_cache(self, task_id: str) -> Optional[dict]:
        return self._read_json(self.transcript_cache_path(task_id))

    def write_transcript_cache(self, task_id: str, payload: dict) -> Path:
        target = self.transcript_cache_path(task_id)
        self._write_json(target, payload)
        return target

    def write_markdown_cache(self, task_id: str, markdown: str) -> Path:
        self.ensure_output_dir()
        target = self.markdown_cache_path(task_id)
        target.write_text(markdown, encoding="utf-8")
        return target

    def read_verification_claim_artifact(self, task_id: str, claim_id: str) -> Optional[dict]:
        return self._read_json(self.verification_claim_path(task_id, claim_id))

    def write_verification_claim_artifact(self, task_id: str, claim_id: str, payload: dict) -> Path:
        target = self.verification_claim_path(task_id, claim_id)
        self._write_json(target, payload)
        return target

    def read_verification_cache(self, kind: str, key: str) -> Optional[dict]:
        return self._read_json(self.verification_cache_path(kind, key))

    def write_verification_cache(self, kind: str, key: str, payload: dict) -> Path:
        target = self.verification_cache_path(kind, key)
        self._write_json(target, payload)
        return target

    def iter_result_files(self) -> Iterator[NoteResultFile]:
        if not self.output_dir.exists():
            return
        for path in self.output_dir.iterdir():
            if not self._is_note_result_file(path):
                continue
            yield NoteResultFile(
                task_id=path.stem,
                path=path,
                modified_at=path.stat().st_mtime,
            )

    def delete_task_files(self, task_id: str) -> int:
        if not self.output_dir.exists():
            return 0

        deleted = 0
        resolved_output_dir = self.output_dir.resolve()
        candidate_paths = [
            self.result_path(task_id),
            self.status_path(task_id),
            self.transcript_cache_path(task_id),
            self.audio_cache_path(task_id),
            self.markdown_cache_path(task_id),
        ]
        for path in candidate_paths:
            try:
                if path.exists() and path.is_file() and path.resolve().parent == resolved_output_dir:
                    path.unlink()
                    deleted += 1
            except Exception as exc:
                logger.warning(f"删除任务文件失败 ({path}): {exc}")
        verification_dir = self.verification_task_dir(task_id)
        try:
            if (
                verification_dir.exists()
                and verification_dir.is_dir()
                and verification_dir.resolve().parent == (resolved_output_dir / "_verification").resolve()
            ):
                shutil.rmtree(verification_dir)
                deleted += 1
        except Exception as exc:
            logger.warning(f"删除核验任务产物失败 ({verification_dir}): {exc}")
        return deleted

    def _read_json(self, path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning(f"读取 JSON 产物失败 ({path}): {exc}")
            return None

    def _write_json(self, path: Path, payload: dict) -> None:
        self.ensure_output_dir()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _is_note_result_file(path: Path) -> bool:
        if path.suffix != ".json":
            return False
        return not any(path.name.endswith(suffix) for suffix in IGNORED_RESULT_SUFFIXES)
