import json
import sqlite3
from types import SimpleNamespace

import pytest

from scripts import migrate_to_fastread as migration


def _legacy_payload():
    return {
        "paper_task": True,
        "paper_document": {
            "id": migration.EIGENBENCH_TASK_ID,
            "title": "EigenBench",
            "authors": ["Old Author"],
            "source_url": "/uploads/eigenbench.pdf",
            "pdf_url": "/uploads/eigenbench.pdf",
            "content_hash": "paper-hash",
            "pages": [{"page": 1, "text": "Published as a conference paper at ICLR 2026"}],
        },
        "audio_meta": {"title": "EigenBench", "platform": "paper", "raw_info": {}},
        "insights": {
            "verification_tasks": [{"id": "retired"}],
            "reading_report": {
                "report_version": "old-report",
                "executive_summary": "报告摘要。需要特别说明的是旧身份未闭合。",
                "key_questions": [
                    {"question": "学术身份是什么？", "answer": "不能视为正式 ICLR 论文。", "evidence": []}
                ],
                "limitations": ["不能视为正式 ICLR 论文"],
            },
        },
    }


def _paper_tasks_schema(connection):
    connection.execute(
        """
        CREATE TABLE paper_tasks (
            task_id TEXT PRIMARY KEY, title TEXT, authors_json TEXT, year INTEGER,
            venue_id TEXT, venue_name TEXT, venue_track TEXT, identity_status TEXT,
            doi TEXT, source_url TEXT, resolved_source_url TEXT, pdf_url TEXT,
            upload_filename TEXT, content_hash TEXT, report_version TEXT,
            collection_folder TEXT, collection_tags_json TEXT, collection_note TEXT
        )
        """
    )


def _migration_fixture(tmp_path):
    source_db = tmp_path / "legacy.db"
    sqlite3.connect(source_db).close()
    legacy_results = tmp_path / "legacy-results"
    legacy_results.mkdir()
    legacy_result = legacy_results / f"{migration.EIGENBENCH_TASK_ID}.json"
    legacy_result.write_text(json.dumps(_legacy_payload(), ensure_ascii=False), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "databases": [
                    {"path": str(source_db), "sha256": migration.sha256_file(source_db)}
                ],
                "task_results": [
                    {
                        "task_id": migration.EIGENBENCH_TASK_ID,
                        "sha256": migration.sha256_file(legacy_result),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return source_db, legacy_results, manifest


def test_eigenbench_artifact_migration_updates_nested_report_atomically():
    migrated = migration.migrate_eigenbench_artifact(_legacy_payload())
    document = migrated["paper_document"]
    report = migrated["insights"]["reading_report"]

    assert document["academic_gate"]["identity_status"] == "confirmed_core"
    assert document["academic_gate"]["gate_passed"] is True
    assert document["formal_record_url"] == migration.EIGENBENCH_RECORD_URL
    assert report["report_version"] == "academic-gate-v3"
    assert report["academic_gate"]["level"] == "A1"
    assert "不能视为正式 ICLR" not in json.dumps(report, ensure_ascii=False)
    assert "verification_tasks" not in migrated["insights"]


def test_insert_task_reads_report_version_from_insights(tmp_path):
    target_db = tmp_path / "fastread.db"
    with sqlite3.connect(target_db) as connection:
        _paper_tasks_schema(connection)
    payload = migration.migrate_eigenbench_artifact(_legacy_payload())

    migration.insert_eigenbench_task(target_db, payload)

    with sqlite3.connect(target_db) as connection:
        row = connection.execute(
            "SELECT task_id, report_version FROM paper_tasks"
        ).fetchone()
    assert row == (migration.EIGENBENCH_TASK_ID, "academic-gate-v3")


def test_preserved_tables_copy_models_and_providers_but_not_legacy_tasks(tmp_path):
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    for path in (source, target):
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE models (id INTEGER PRIMARY KEY, name TEXT)")
            connection.execute("CREATE TABLE providers (id INTEGER PRIMARY KEY, name TEXT)")
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE video_tasks (id INTEGER PRIMARY KEY, platform TEXT)")
        connection.execute("INSERT INTO models VALUES (1, 'model-a')")
        connection.execute("INSERT INTO providers VALUES (1, 'provider-a')")
        connection.execute("INSERT INTO video_tasks VALUES (1, 'legacy')")

    migration.copy_preserved_tables(source, target)

    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT name FROM models").fetchall() == [("model-a",)]
        assert connection.execute("SELECT name FROM providers").fetchall() == [("provider-a",)]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "video_tasks" not in tables


def test_failed_migration_never_switches_partial_target(monkeypatch, tmp_path):
    source_db, legacy_results, manifest = _migration_fixture(tmp_path)
    target_db = tmp_path / "fastread.db"
    target_results = tmp_path / "paper-results"
    args = SimpleNamespace(
        backend_root=tmp_path,
        source_db=source_db,
        legacy_results=legacy_results,
        target_db=target_db,
        target_results=target_results,
        snapshot_manifest=manifest,
    )
    monkeypatch.setattr(
        migration,
        "create_target_schema",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("schema failed")),
    )

    with pytest.raises(RuntimeError, match="schema failed"):
        migration.migrate(args)

    assert not target_db.exists()
    assert not target_results.exists()
    assert not (tmp_path / ".fastread.db.migrating").exists()
    assert not (tmp_path / ".paper-results.migrating").exists()


def test_repeated_migration_is_idempotent_after_valid_target(tmp_path):
    source_db, legacy_results, manifest = _migration_fixture(tmp_path)
    target_db = tmp_path / "fastread.db"
    target_results = tmp_path / "paper-results"
    target_results.mkdir()
    payload = migration.migrate_eigenbench_artifact(_legacy_payload())
    (target_results / f"{migration.EIGENBENCH_TASK_ID}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    with sqlite3.connect(target_db) as connection:
        _paper_tasks_schema(connection)
    migration.insert_eigenbench_task(target_db, payload)
    args = SimpleNamespace(
        backend_root=tmp_path,
        source_db=source_db,
        legacy_results=legacy_results,
        target_db=target_db,
        target_results=target_results,
        snapshot_manifest=manifest,
    )

    assert migration.migrate(args) == "already_migrated"
    migration.validate_target(
        target_db,
        target_results / f"{migration.EIGENBENCH_TASK_ID}.json",
    )
