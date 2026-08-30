from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_inventory(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "tables": {
                table: {
                    "count": connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0],
                    "columns": [
                        row[1]
                        for row in connection.execute(f'PRAGMA table_info("{table}")')
                    ],
                }
                for table in tables
            },
        }


def backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)


def classify_result(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    parse_error = ""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        payload = loaded if isinstance(loaded, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        parse_error = type(exc).__name__

    task_id = path.stem
    platform = str((payload.get("audio_meta") or {}).get("platform") or "")
    if payload.get("paper_task") is True or platform == "paper":
        task_type = "paper"
    elif payload.get("verification_task") is True or platform == "verification":
        task_type = "verification"
    else:
        task_type = "video_or_legacy"

    associated = sorted(
        str(candidate)
        for candidate in path.parent.glob(f"{task_id}*")
        if candidate.is_file() and candidate != path
    )
    verification_dir = path.parent / "_verification" / task_id
    if verification_dir.is_dir():
        associated.extend(
            str(candidate)
            for candidate in sorted(verification_dir.rglob("*"))
            if candidate.is_file()
        )

    document = payload.get("paper_document") or {}
    return {
        "task_id": task_id,
        "type": task_type,
        "platform": platform,
        "title": str(document.get("title") or (payload.get("audio_meta") or {}).get("title") or ""),
        "content_hash": str(document.get("content_hash") or ""),
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "associated_artifacts": associated,
        "parse_error": parse_error,
    }


def copy_runtime_tree(source: Path, destination: Path) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    if not source.exists():
        return copied
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(
            {
                "relative_path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return copied


def git_output(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def build_snapshot(
    repo_root: Path,
    snapshot_root: Path,
    *,
    database_names: tuple[str, ...] = (),
) -> Path:
    backend_root = repo_root / "backend"
    snapshot_root.mkdir(parents=True, exist_ok=False)

    databases: list[dict[str, Any]] = []
    discovered_names = database_names or tuple(path.name for path in sorted(backend_root.glob("*.db")))
    for name in discovered_names:
        source = backend_root / name
        if not source.exists():
            continue
        record = sqlite_inventory(source)
        destination = snapshot_root / "databases" / name
        backup_sqlite(source, destination)
        record["snapshot_path"] = str(destination)
        record["snapshot_sha256"] = sha256_file(destination)
        databases.append(record)

    note_results_dir = backend_root / "note_results"
    task_results = [
        classify_result(path)
        for path in sorted(note_results_dir.glob("*.json"))
        if not path.name.endswith((".status.json", "_audio.json", "_transcript.json"))
    ]
    note_files = copy_runtime_tree(note_results_dir, snapshot_root / "note_results")
    paper_files = copy_runtime_tree(backend_root / "paper_results", snapshot_root / "paper_results")
    upload_files = copy_runtime_tree(backend_root / "uploads", snapshot_root / "uploads")
    vector_files = copy_runtime_tree(backend_root / "vector_db", snapshot_root / "vector_db")

    tracked_files = [line for line in git_output(repo_root, "ls-files").splitlines() if line]
    worktree_status = [
        line for line in git_output(repo_root, "status", "--porcelain=v1", "--untracked-files=all").splitlines() if line
    ]
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(repo_root),
        "snapshot_root": str(snapshot_root),
        "git": {
            "head": git_output(repo_root, "rev-parse", "HEAD").strip(),
            "branch": git_output(repo_root, "branch", "--show-current").strip(),
            "tracked_files": tracked_files,
            "worktree_status": worktree_status,
        },
        "databases": databases,
        "task_results": task_results,
        "runtime_artifacts": {
            "note_results": note_files,
            "paper_results": paper_files,
            "uploads": upload_files,
            "vector_db": vector_files,
            "verification_cache_owner": "legacy verification pipeline; do not migrate",
            "browser_local_state": {
                "owner": "client-managed Zustand/IndexedDB or extension storage",
                "snapshot_status": "not stored in repository runtime data",
            },
        },
        "migration_decision": {
            "preserve_task_ids": [
                result["task_id"] for result in task_results if result["type"] == "paper"
            ],
            "discard_types": ["video_or_legacy", "verification"],
            "preserve_relational_tables": [
                "models",
                "providers",
                "paper_annotations",
                "paper_candidates",
                "research_topics",
                "research_topic_papers",
                "topic_evidence_items",
                "topic_syntheses",
                "fastwrite_handoffs",
            ],
        },
    }
    manifest_path = snapshot_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the one-time FastRead migration snapshot.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", action="append", default=[], help="database filename to include; defaults to all backend/*.db")
    args = parser.parse_args()
    manifest_path = build_snapshot(
        args.repo_root.resolve(),
        args.output.resolve(),
        database_names=tuple(args.database),
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
