from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.db.engine import get_db
from app.db.models.paper_tasks import MetadataMigrationRun
from app.db.paper_task_dao import get_paper_task, upsert_paper_task
from app.db.related_work_dao import invalidate_related_work
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.academic_identity_resolver import resolve_document_claim_record
from app.services.metadata_normalization import (
    METADATA_PARSER_VERSION,
    METADATA_SCHEMA_VERSION,
    METADATA_STRATEGY_VERSION,
    normalize_paper_metadata,
)
from app.services.paper_fetching import parse_pdf_bytes
from app.core.settings import get_settings
from app.utils.logger import get_logger


logger = get_logger(__name__)


def _diff(before: dict, after: dict) -> dict:
    keys = sorted(set(before) | set(after))
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in keys
        if before.get(key) != after.get(key)
    }


class MetadataMigrationService:
    """Dry-runnable, per-task atomic and replayable metadata migration."""

    def __init__(self, artifacts: PaperArtifactRepository | None = None, resolver=None):
        self.artifacts = artifacts or PaperArtifactRepository()
        self._resolver = resolver or resolve_document_claim_record

    @staticmethod
    def _record_run(run_id: str, report: dict) -> None:
        db = next(get_db())
        try:
            record = db.query(MetadataMigrationRun).filter_by(id=run_id).first()
            if record is None:
                record = MetadataMigrationRun(id=run_id)
                db.add(record)
            record.target_schema_version = METADATA_SCHEMA_VERSION
            record.dry_run = int(bool(report["dry_run"]))
            record.status = report["status"]
            record.scanned_count = report["scanned_count"]
            record.eligible_count = report["eligible_count"]
            record.migrated_count = report["migrated_count"]
            record.failed_count = report["failed_count"]
            record.report_json = json.dumps(report, ensure_ascii=False)
            if report["status"] != "running":
                record.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _normalize_result(self, result: dict) -> tuple[dict, dict]:
        document = result.get("paper_document") or {}
        pages = document.get("pages") or []
        first_page = str((pages[0] if pages else {}).get("text") or "")
        # Older parser versions collapsed PDF line boundaries. Reparse only the
        # owned source PDF for metadata candidates; persisted pages remain byte-for-
        # byte untouched so quotes, page numbers and user artifacts stay stable.
        if "\n" not in first_page:
            settings = get_settings()
            upload_prefix = settings.uploads_path.rstrip("/") + "/"
            parsed_path = urlparse(str(document.get("pdf_url") or document.get("source_url") or "")).path
            if parsed_path.startswith(upload_prefix):
                filename = Path(parsed_path).name
                source_pdf = (settings.uploads_dir / filename).resolve()
                if source_pdf.parent == settings.uploads_dir.resolve() and source_pdf.is_file():
                    reparsed = parse_pdf_bytes(source_pdf.read_bytes(), str(document.get("source_url") or ""))
                    spans = reparsed.get("page_spans") or []
                    text = str(reparsed.get("text") or "")
                    if spans:
                        first = spans[0]
                        first_page = text[int(first.get("start") or 0) : int(first.get("end") or 0)]
        existing_gate = document.get("academic_gate") or {}
        existing_verified = document.get("verified_identity") or {}
        raw = document.get("raw_metadata") or {
            "title": document.get("title"),
            "authors": document.get("authors"),
            "year": document.get("year"),
            "venue": document.get("venue"),
            "doi": document.get("doi"),
            "url": document.get("source_url"),
            "canonical_url": document.get("resolved_source_url"),
            "pdf_url": document.get("pdf_url"),
            "content_hash": document.get("content_hash"),
            "parser": document.get("parser"),
            "parser_version": document.get("parser_version"),
            "source_status": document.get("source_status"),
            "document_claimed_metadata": document.get("document_claimed_metadata") or {},
            "registry_record_verified": bool(
                existing_gate.get("registry_record_verified")
                or (existing_verified.get("status") == "verified" and existing_gate.get("identity_source") == "conference_registry")
            ),
            "registry_name": existing_gate.get("registry_name") or existing_verified.get("registry_name") or "",
            "registry_record_url": existing_gate.get("registry_record_url") or existing_verified.get("official_record_url") or document.get("formal_record_url") or "",
            "verified_academic_metadata": (
                {
                    "title": existing_gate.get("title") or document.get("title"),
                    "authors": existing_gate.get("authors") or document.get("authors") or [],
                    "year": existing_gate.get("year") or document.get("year"),
                    "published_at": str(existing_gate.get("year") or document.get("year") or ""),
                    "venue": (existing_gate.get("venue") or document.get("venue") or {}).get("short_name")
                    if isinstance(existing_gate.get("venue") or document.get("venue"), dict)
                    else existing_gate.get("venue") or document.get("venue") or "",
                    "source_url": existing_gate.get("registry_record_url") or document.get("formal_record_url") or "",
                }
                if existing_gate.get("registry_record_verified")
                else {}
            ),
        }
        claim = raw.get("document_claimed_metadata") or {}
        resolved = {}
        if claim:
            try:
                preliminary = normalize_paper_metadata(
                    raw,
                    first_page_text=first_page,
                    unverified_supplement=document.get("unverified_supplement") or {},
                )
                preliminary_metadata = preliminary["normalized_metadata"]
                resolver_claim = {
                    **claim,
                    "title": preliminary_metadata.get("title") or claim.get("title"),
                    "authors": preliminary_metadata.get("authors") or claim.get("authors") or [],
                    "year": preliminary_metadata.get("year") or claim.get("year"),
                }
                resolved = self._resolver(resolver_claim) or {}
            except Exception as exc:
                logger.warning(f"元数据迁移官方身份闭合失败，保留未验证身份 task={document.get('id')}: {exc}")
        contract = normalize_paper_metadata(
            raw,
            first_page_text=first_page,
            unverified_supplement=document.get("unverified_supplement") or {},
            resolved_identity=resolved,
        )
        normalized = contract["normalized_metadata"]
        verified = contract["verified_identity"]
        migrated = dict(result)
        migrated_document = dict(document)
        migrated_document.update(
            {
                "title": normalized["title"],
                "authors": normalized["authors"],
                "year": normalized["year"],
                "venue": normalized["venue"],
                "doi": normalized["doi"],
                "academic_gate": verified["academic_gate"],
                "formal_record_url": verified.get("official_record_url") or "",
                "raw_metadata": contract["raw_metadata"],
                "normalized_metadata": normalized,
                "verified_identity": verified,
                "metadata_contract": {
                    key: contract[key]
                    for key in (
                        "schema_version", "parser_version", "strategy_version", "execution_status",
                        "fallback_reasons", "normalized_at", "candidate_boundaries",
                    )
                },
            }
        )
        migrated["paper_document"] = migrated_document
        migrated.setdefault("insights", {})["academic_gate"] = verified["academic_gate"]
        return migrated, contract

    def run(self, *, dry_run: bool = True, task_ids: set[str] | None = None) -> dict:
        run_id = uuid.uuid4().hex
        report = {
            "run_id": run_id,
            "target_schema_version": METADATA_SCHEMA_VERSION,
            "parser_version": METADATA_PARSER_VERSION,
            "strategy_version": METADATA_STRATEGY_VERSION,
            "dry_run": bool(dry_run),
            "status": "running",
            "scanned_count": 0,
            "eligible_count": 0,
            "migrated_count": 0,
            "failed_count": 0,
            "tasks": [],
            "index_rebuild_required": False,
        }
        self._record_run(run_id, report)
        for result_file in self.artifacts.iter_result_files() or []:
            if task_ids and result_file.task_id not in task_ids:
                continue
            report["scanned_count"] += 1
            original = self.artifacts.read_result(result_file.task_id) or {}
            document = original.get("paper_document") or {}
            current = (document.get("metadata_contract") or {}).get("schema_version") or ""
            if original.get("paper_task") is not True or current == METADATA_SCHEMA_VERSION:
                report["tasks"].append(
                    {"task_id": result_file.task_id, "status": "skipped", "reason": "already_current_or_not_paper"}
                )
                continue
            report["eligible_count"] += 1
            try:
                migrated, contract = self._normalize_result(original)
                before = {
                    key: document.get(key)
                    for key in ("title", "authors", "year", "venue", "doi", "formal_record_url")
                }
                after_document = migrated["paper_document"]
                after = {key: after_document.get(key) for key in before}
                task_report = {
                    "task_id": result_file.task_id,
                    "status": "dry_run" if dry_run else "migrated",
                    "diff": _diff(before, after),
                    "execution_status": contract["execution_status"],
                    "fallback_reasons": contract["fallback_reasons"],
                    "invalidated": {},
                }
                if task_report["diff"]:
                    report["index_rebuild_required"] = True
                if not dry_run:
                    metadata_before = get_paper_task(result_file.task_id)
                    self.artifacts.write_result(result_file.task_id, migrated)
                    try:
                        upsert_paper_task(
                            {
                                **(metadata_before or {}),
                                "task_id": result_file.task_id,
                                "title": after_document["title"],
                                "authors": after_document["authors"],
                                "year": after_document["year"],
                                "venue": after_document["venue"],
                                "identity_status": after_document["academic_gate"]["identity_status"],
                                "doi": after_document["doi"],
                                "source_url": after_document.get("source_url") or "",
                                "resolved_source_url": after_document.get("resolved_source_url") or "",
                                "pdf_url": after_document.get("pdf_url") or "",
                                "filename": after_document.get("filename") or "",
                                "content_hash": after_document.get("content_hash") or "",
                                "raw_metadata": contract["raw_metadata"],
                                "normalized_metadata": contract["normalized_metadata"],
                                "verified_identity": contract["verified_identity"],
                                "metadata_schema_version": contract["schema_version"],
                                "metadata_parser_version": contract["parser_version"],
                                "metadata_strategy_version": contract["strategy_version"],
                                "metadata_execution_status": contract["execution_status"],
                                "metadata_fallback_reasons": contract["fallback_reasons"],
                            }
                        )
                        task_report["invalidated"] = invalidate_related_work(result_file.task_id)
                    except Exception:
                        self.artifacts.write_result(result_file.task_id, original)
                        raise
                    report["migrated_count"] += 1
                report["tasks"].append(task_report)
            except Exception as exc:
                report["failed_count"] += 1
                report["tasks"].append(
                    {"task_id": result_file.task_id, "status": "failed", "reason": f"{type(exc).__name__}:{exc}"}
                )
        report["status"] = "completed_with_failures" if report["failed_count"] else "completed"
        self._record_run(run_id, report)
        return report
