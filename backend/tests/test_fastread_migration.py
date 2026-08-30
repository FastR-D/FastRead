from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.metadata_migration_service import MetadataMigrationService
from app.services.metadata_normalization import METADATA_SCHEMA_VERSION


def _legacy_payload(task_id="paper-fixture"):
    return {
        "paper_task": True,
        "paper_document": {
            "id": task_id,
            "title": "A Useful Study\nAlice Example\nExample University",
            "authors": ["Example University", "Alice Example"],
            "source_url": "/uploads/paper.pdf",
            "pdf_url": "/uploads/paper.pdf",
            "content_hash": "paper-hash",
            "document_claimed_metadata": {
                "title": "A Useful Study",
                "authors": ["Alice Example"],
                "year": 2025,
                "venue": "",
            },
            "pages": [{"page": 1, "text": "A Useful Study\nAlice Example\nExample University\nalice@example.edu\nAbstract\nBody"}],
        },
        "insights": {"personal_summary": "user-owned", "reading_report": {"report_version": "r1"}},
    }


def test_dry_run_is_non_mutating_and_reports_diff(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_result("paper-fixture", _legacy_payload())
    monkeypatch.setattr(MetadataMigrationService, "_record_run", staticmethod(lambda *_args: None))
    service = MetadataMigrationService(artifacts, resolver=lambda _claim: {})

    report = service.run(dry_run=True)

    assert report["eligible_count"] == 1
    assert report["migrated_count"] == 0
    assert report["tasks"][0]["status"] == "dry_run"
    assert artifacts.read_result("paper-fixture")["paper_document"]["title"].startswith("A Useful Study\n")


def test_apply_preserves_pages_reports_and_user_content(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    original = _legacy_payload()
    artifacts.write_result("paper-fixture", original)
    monkeypatch.setattr(MetadataMigrationService, "_record_run", staticmethod(lambda *_args: None))
    monkeypatch.setattr("app.services.metadata_migration_service.get_paper_task", lambda _task_id: {})
    monkeypatch.setattr("app.services.metadata_migration_service.upsert_paper_task", lambda payload: payload)
    monkeypatch.setattr("app.services.metadata_migration_service.invalidate_related_work", lambda _task_id: {"related_work_snapshots": 1, "smart_selections": 1})

    report = MetadataMigrationService(artifacts, resolver=lambda _claim: {}).run(dry_run=False)
    migrated = artifacts.read_result("paper-fixture")

    assert report["migrated_count"] == 1
    assert migrated["paper_document"]["metadata_contract"]["schema_version"] == METADATA_SCHEMA_VERSION
    assert migrated["paper_document"]["title"] == "A Useful Study"
    assert migrated["paper_document"]["authors"] == ["Alice Example"]
    assert migrated["paper_document"]["pages"] == original["paper_document"]["pages"]
    assert migrated["insights"]["personal_summary"] == "user-owned"
    assert migrated["insights"]["reading_report"] == {"report_version": "r1"}


def test_current_version_is_skipped(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    payload = _legacy_payload()
    payload["paper_document"]["metadata_contract"] = {"schema_version": METADATA_SCHEMA_VERSION}
    artifacts.write_result("paper-fixture", payload)
    monkeypatch.setattr(MetadataMigrationService, "_record_run", staticmethod(lambda *_args: None))

    report = MetadataMigrationService(artifacts).run(dry_run=False)

    assert report["eligible_count"] == 0
    assert report["tasks"][0]["reason"] == "already_current_or_not_paper"
