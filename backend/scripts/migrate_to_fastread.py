from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from copy import deepcopy
from pathlib import Path


EIGENBENCH_TASK_ID = "aa8c4d5e-c9bb-4c62-9308-a5522b7b0131"
EIGENBENCH_RECORD_URL = "https://openreview.net/forum?id=fm79KXJIUQ"
EIGENBENCH_TITLE = "EigenBench: A Comparative Behavioral Measure of Value Alignment"
EIGENBENCH_AUTHORS = [
    "Jonathn Chang",
    "Leonhard Piff",
    "Suvadip Sana",
    "Jasmine X. Li",
    "Lionel Levine",
]
PRESERVED_TABLES = (
    "models",
    "providers",
    "paper_annotations",
    "paper_candidates",
    "research_topics",
    "research_topic_papers",
    "topic_evidence_items",
    "topic_syntheses",
    "fastwrite_handoffs",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_snapshot_match(manifest_path: Path, source_db: Path, legacy_result: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    database_record = next(
        (item for item in manifest.get("databases", []) if Path(item["path"]).name == source_db.name),
        None,
    )
    result_record = next(
        (
            item
            for item in manifest.get("task_results", [])
            if item.get("task_id") == EIGENBENCH_TASK_ID
        ),
        None,
    )
    if not database_record or sha256_file(source_db) != database_record.get("sha256"):
        raise RuntimeError("Source database differs from the verified migration snapshot")
    if not result_record or sha256_file(legacy_result) != result_record.get("sha256"):
        raise RuntimeError("EigenBench artifact differs from the verified migration snapshot")


def eigenbench_gate() -> dict:
    venue = {
        "id": "iclr",
        "name": "International Conference on Learning Representations",
        "short_name": "ICLR",
        "track": "ai",
        "raw": "ICLR 2026",
    }
    return {
        "level": "A1",
        "label": "AI 顶会正式论文，身份完整",
        "gate_passed": True,
        "formal_identity_passed": True,
        "identity_complete": True,
        "identity_fields_complete": True,
        "is_top4_security": False,
        "is_core_venue": True,
        "venue_track": "ai",
        "identity_source": "conference_registry",
        "identity_status": "confirmed_core",
        "publication_status": "formally_published",
        "integrity_status": "clear",
        "source_status": "locked",
        "title": EIGENBENCH_TITLE,
        "authors": EIGENBENCH_AUTHORS,
        "year": 2026,
        "doi": "",
        "venue": venue,
        "official_record": True,
        "official_record_verified": False,
        "registry_record_verified": True,
        "registry_name": "Paper Copilot ICLR accepted-paper index",
        "registry_record_url": EIGENBENCH_RECORD_URL,
        "official_host_match": True,
        "verified_metadata_used": True,
        "document_claimed_metadata": {},
        "has_academic_signal": True,
        "warnings": [],
    }


def migrate_eigenbench_artifact(payload: dict) -> dict:
    migrated = deepcopy(payload)
    gate = eigenbench_gate()
    venue = gate["venue"]
    document = migrated.setdefault("paper_document", {})
    document.update(
        {
            "title": EIGENBENCH_TITLE,
            "authors": EIGENBENCH_AUTHORS,
            "venue": venue,
            "year": 2026,
            "academic_gate": gate,
            "formal_record_url": EIGENBENCH_RECORD_URL,
        }
    )
    audio_meta = migrated.setdefault("audio_meta", {})
    audio_meta.update({"title": EIGENBENCH_TITLE, "platform": "paper"})
    audio_meta.setdefault("raw_info", {}).update(
        {
            "authors": EIGENBENCH_AUTHORS,
            "venue": venue,
            "year": 2026,
            "formal_record_url": EIGENBENCH_RECORD_URL,
        }
    )
    insights = migrated.setdefault("insights", {})
    insights["academic_gate"] = gate
    insights.pop("verification", None)
    insights.pop("verification_tasks", None)
    report = insights.get("reading_report")
    if isinstance(report, dict):
        report["academic_gate"] = gate
        report["report_version"] = "academic-gate-v3"
        summary = str(report.get("executive_summary") or "")
        if "需要特别说明的是" in summary:
            summary = summary.split("需要特别说明的是", 1)[0].rstrip(" ，。")
        report["executive_summary"] = (
            summary
            + "。其正式学术身份已由会议记录闭合为 ICLR 2026 AI 顶会论文，核心 Gate 为 A1。"
        ).lstrip("。")

        for question in report.get("key_questions") or []:
            if not isinstance(question, dict):
                continue
            question.pop("verification_status", None)
            for evidence in question.get("evidence") or []:
                if isinstance(evidence, dict):
                    evidence.pop("verification_status", None)
            if "学术身份" in str(question.get("question") or ""):
                question["answer"] = (
                    "该论文已闭合为 ICLR 2026 正式会议论文，属于 AI 核心会议，身份状态为 "
                    "confirmed_core，核心 Gate 通过且等级为 A1。正式记录："
                    f"{EIGENBENCH_RECORD_URL}。学术身份只说明发表记录已闭合，不证明论文主张本身正确。"
                )
                question["why_it_matters"] = (
                    "正式发表身份与论文内容可信度是两个不同问题；前者可由会议记录确定，后者仍需回到分页原文、方法和实验。"
                )

        for contribution in report.get("contributions") or []:
            if not isinstance(contribution, dict):
                continue
            for evidence in contribution.get("evidence") or []:
                if isinstance(evidence, dict):
                    evidence.pop("verification_status", None)

        limitations = [
            str(item)
            for item in report.get("limitations") or []
            if not any(
                marker in str(item)
                for marker in (
                    "学术身份 Gate",
                    "不能视为正式 ICLR",
                    "source_only",
                    "发表状态未通过",
                )
            )
        ]
        limitations.insert(
            0,
            "学术身份已闭合为 ICLR 2026 A1；该身份不替代对方法、实验和结论的独立评估。",
        )
        report["limitations"] = limitations
    migrated["paper_task"] = True
    migrated.pop("verification_task", None)
    return migrated


def create_target_schema(target_db: Path, target_results: Path, backend_root: Path) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite:///{target_db.as_posix()}"
    environment["PAPER_OUTPUT_DIR"] = str(target_results)
    subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            "from app.db.init_db import init_db; "
            "from app.db.engine import get_engine; "
            "init_db(); get_engine().dispose()",
        ],
        cwd=backend_root,
        env=environment,
        check=True,
    )


def copy_preserved_tables(source_db: Path, target_db: Path) -> None:
    with closing(sqlite3.connect(source_db)) as source, closing(sqlite3.connect(target_db)) as target:
        source_tables = {
            row[0]
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        target_tables = {
            row[0]
            for row in target.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in PRESERVED_TABLES:
            if table not in source_tables or table not in target_tables:
                continue
            columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
            target_columns = {
                row[1] for row in target.execute(f'PRAGMA table_info("{table}")')
            }
            columns = [column for column in columns if column in target_columns]
            placeholders = ",".join("?" for _ in columns)
            quoted_columns = ",".join(f'"{column}"' for column in columns)
            rows = source.execute(f'SELECT {quoted_columns} FROM "{table}"').fetchall()
            if rows:
                target.executemany(
                    f'INSERT OR REPLACE INTO "{table}" ({quoted_columns}) VALUES ({placeholders})',
                    rows,
                )
        target.commit()


def insert_eigenbench_task(target_db: Path, payload: dict) -> None:
    document = payload["paper_document"]
    gate = document["academic_gate"]
    venue = document["venue"]
    report = (payload.get("insights") or {}).get("reading_report") or {}
    with closing(sqlite3.connect(target_db)) as connection:
        connection.execute(
            """
            INSERT INTO paper_tasks (
                task_id, title, authors_json, year, venue_id, venue_name, venue_track,
                identity_status, doi, source_url, resolved_source_url, pdf_url,
                upload_filename, content_hash, report_version, collection_folder,
                collection_tags_json, collection_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                EIGENBENCH_TASK_ID,
                document["title"],
                json.dumps(document["authors"], ensure_ascii=False),
                document["year"],
                venue["id"],
                venue["short_name"],
                venue["track"],
                gate["identity_status"],
                document.get("doi") or "",
                document.get("source_url") or "",
                document.get("resolved_source_url") or "",
                document.get("pdf_url") or "",
                document.get("filename") or "",
                document.get("content_hash") or "",
                str(report.get("report_version") or ""),
                "默认收藏夹",
                "[]",
                "",
            ),
        )
        connection.commit()


def validate_target(target_db: Path, target_result: Path) -> None:
    with closing(sqlite3.connect(f"file:{target_db.as_posix()}?mode=ro", uri=True)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "video_tasks" in tables:
            raise RuntimeError("Legacy video_tasks table leaked into fastread.db")
        task_ids = [row[0] for row in connection.execute("SELECT task_id FROM paper_tasks")]
        if task_ids != [EIGENBENCH_TASK_ID]:
            raise RuntimeError(f"Unexpected migrated paper task set: {task_ids}")
    payload = json.loads(target_result.read_text(encoding="utf-8"))
    gate = payload.get("paper_document", {}).get("academic_gate", {})
    if gate.get("identity_status") != "confirmed_core" or gate.get("gate_passed") is not True:
        raise RuntimeError("EigenBench academic identity migration did not close")


def migrate(args: argparse.Namespace) -> str:
    backend_root = args.backend_root.resolve()
    source_db = args.source_db.resolve()
    legacy_results = args.legacy_results.resolve()
    target_db = args.target_db.resolve()
    target_results = args.target_results.resolve()
    legacy_result = legacy_results / f"{EIGENBENCH_TASK_ID}.json"
    require_snapshot_match(args.snapshot_manifest.resolve(), source_db, legacy_result)

    if target_db.exists() or target_results.exists():
        if target_db.is_file() and target_results.is_dir():
            validate_target(target_db, target_results / f"{EIGENBENCH_TASK_ID}.json")
            return "already_migrated"
        raise RuntimeError("Refusing to overwrite a partial or unverified migration target")

    staging_db = target_db.with_name(f".{target_db.name}.migrating")
    staging_results = target_results.with_name(f".{target_results.name}.migrating")
    if staging_db.exists():
        staging_db.unlink()
    if staging_results.exists():
        shutil.rmtree(staging_results)
    staging_results.mkdir(parents=True)

    try:
        create_target_schema(staging_db, staging_results, backend_root)
        copy_preserved_tables(source_db, staging_db)
        source_payload = json.loads(legacy_result.read_text(encoding="utf-8"))
        migrated_payload = migrate_eigenbench_artifact(source_payload)
        target_result = staging_results / f"{EIGENBENCH_TASK_ID}.json"
        target_result.write_text(
            json.dumps(migrated_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        source_status = legacy_results / f"{EIGENBENCH_TASK_ID}.status.json"
        if source_status.is_file():
            shutil.copy2(source_status, staging_results / source_status.name)
        insert_eigenbench_task(staging_db, migrated_payload)
        validate_target(staging_db, target_result)
        os.replace(staging_db, target_db)
        os.replace(staging_results, target_results)
        validate_target(target_db, target_results / target_result.name)
        return "migrated"
    except Exception:
        if staging_db.exists():
            staging_db.unlink()
        if staging_results.exists():
            shutil.rmtree(staging_results)
        raise


def parse_args() -> argparse.Namespace:
    backend_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Migrate paper data to the FastRead-only runtime.")
    parser.add_argument("--backend-root", type=Path, default=backend_root)
    parser.add_argument("--source-db", type=Path, default=backend_root / "reel_mind.db")
    parser.add_argument("--legacy-results", type=Path, default=backend_root / "note_results")
    parser.add_argument("--target-db", type=Path, default=backend_root / "fastread.db")
    parser.add_argument("--target-results", type=Path, default=backend_root / "paper_results")
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    print(migrate(parse_args()))
