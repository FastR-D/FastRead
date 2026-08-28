from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from app.core.settings import get_settings
from app.enmus.task_status_enums import TaskStatus


_SAFE_COMPONENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _validated_task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or not _SAFE_COMPONENT_RE.fullmatch(task_id):
        raise ValueError("Invalid task_id")
    return task_id


def _lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@dataclass(frozen=True)
class PaperResultFile:
    task_id: str
    path: Path
    modified_at: float


class PaperArtifactRepository:
    """Atomic storage for paper documents and their derived reading artifacts."""

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir is not None else get_settings().paper_output_dir

    def ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str, suffix: str) -> Path:
        task_id = _validated_task_id(task_id)
        candidate = self.output_dir / f"{task_id}{suffix}"
        candidate.resolve().relative_to(self.output_dir.resolve())
        return candidate

    def result_path(self, task_id: str) -> Path:
        return self._path(task_id, ".json")

    def status_path(self, task_id: str) -> Path:
        return self._path(task_id, ".status.json")

    def result_exists(self, task_id: str) -> bool:
        return self.result_path(task_id).is_file()

    def read_result(self, task_id: str) -> dict | None:
        return self._read_json(self.result_path(task_id))

    def write_result(self, task_id: str, payload: dict) -> None:
        target = self.result_path(task_id)
        with _lock(target):
            self._write_json(target, payload)

    def update_result(self, task_id: str, mutator: Callable[[dict], dict | None]) -> dict:
        target = self.result_path(task_id)
        with _lock(target):
            payload = self._read_json(target)
            if payload is None:
                raise ValueError("论文任务不存在")
            updated = mutator(payload) or payload
            if not isinstance(updated, dict):
                raise TypeError("result mutator must return a dict or None")
            self._write_json(target, updated)
            return updated

    def read_status(self, task_id: str) -> dict | None:
        return self._read_json(self.status_path(task_id))

    def read_status_or_success(self, task_id: str) -> dict:
        return self.read_status(task_id) or {"status": TaskStatus.SUCCESS.value}

    def write_status(self, task_id: str, status: str | TaskStatus, message: str | None = None) -> None:
        payload = {"status": status.value if isinstance(status, TaskStatus) else status}
        if message:
            payload["message"] = message
        self._write_json(self.status_path(task_id), payload)

    def iter_result_files(self) -> Iterator[PaperResultFile]:
        if not self.output_dir.is_dir():
            return
        for path in sorted(self.output_dir.glob("*.json")):
            if path.name.endswith(".status.json"):
                continue
            yield PaperResultFile(path.stem, path, path.stat().st_mtime)

    def delete_task_files(self, task_id: str) -> int:
        deleted = 0
        for path in (self.result_path(task_id), self.status_path(task_id)):
            if path.is_file():
                path.unlink()
                deleted += 1
        return deleted

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.is_file():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Paper artifact must be a JSON object: {path}")
        return loaded

    def _write_json(self, path: Path, payload: dict) -> None:
        self.ensure_output_dir()
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
