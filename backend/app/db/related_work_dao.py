from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.engine import get_db
from app.db.models.paper_tasks import RelatedWorkSelectionRecord, RelatedWorkSnapshotRecord


def get_related_work_by_cache_key(cache_key: str) -> dict | None:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSnapshotRecord).filter_by(cache_key=cache_key).first()
        return _to_dict(record) if record else None
    finally:
        db.close()


def get_latest_related_work(task_id: str) -> dict | None:
    db = next(get_db())
    try:
        record = (
            db.query(RelatedWorkSnapshotRecord)
            .filter_by(task_id=task_id)
            .order_by(RelatedWorkSnapshotRecord.generated_at.desc())
            .first()
        )
        return _to_dict(record) if record else None
    finally:
        db.close()


def get_related_work_by_id(snapshot_id: str) -> dict | None:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSnapshotRecord).filter_by(id=snapshot_id).first()
        return _to_dict(record) if record else None
    finally:
        db.close()


def save_related_work(snapshot: dict) -> dict:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSnapshotRecord).filter_by(cache_key=snapshot["cache_key"]).first()
        if record is None:
            record = RelatedWorkSnapshotRecord(id=snapshot["id"], cache_key=snapshot["cache_key"])
            db.add(record)
        record.task_id = snapshot["paper_id"]
        record.paper_content_hash = snapshot["paper_content_hash"]
        record.report_version = snapshot["report_version"]
        record.search_backend = snapshot["search_backend"]
        record.anchors_json = json.dumps(snapshot["anchors"], ensure_ascii=False)
        record.neighbors_json = json.dumps(snapshot["neighbors"], ensure_ascii=False)
        record.rejected_neighbors_json = json.dumps(snapshot.get("rejected_neighbors") or [], ensure_ascii=False)
        record.provider_status_json = json.dumps(snapshot["provider_status"], ensure_ascii=False)
        generated_at = snapshot.get("generated_at")
        record.generated_at = (
            datetime.fromisoformat(generated_at.replace("Z", "+00:00")).replace(tzinfo=None)
            if generated_at
            else datetime.now(timezone.utc).replace(tzinfo=None)
        )
        db.commit()
        db.refresh(record)
        return _to_dict(record)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _to_dict(record: RelatedWorkSnapshotRecord) -> dict:
    return {
        "id": record.id,
        "paper_id": record.task_id,
        "paper_content_hash": record.paper_content_hash,
        "report_version": record.report_version,
        "cache_key": record.cache_key,
        "anchors": json.loads(record.anchors_json or "[]"),
        "neighbors": json.loads(record.neighbors_json or "[]"),
        "rejected_neighbors": json.loads(record.rejected_neighbors_json or "[]"),
        "provider_status": json.loads(record.provider_status_json or "{}"),
        "search_backend": record.search_backend,
        "generated_at": record.generated_at.replace(tzinfo=timezone.utc).isoformat()
        if record.generated_at
        else "",
    }


def get_selection_by_cache_key(cache_key: str) -> dict | None:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSelectionRecord).filter_by(cache_key=cache_key).first()
        return _selection_to_dict(record) if record else None
    finally:
        db.close()


def get_selection_by_id(selection_id: str) -> dict | None:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSelectionRecord).filter_by(id=selection_id).first()
        return _selection_to_dict(record) if record else None
    finally:
        db.close()


def get_latest_selection(task_id: str, snapshot_id: str = "") -> dict | None:
    db = next(get_db())
    try:
        query = db.query(RelatedWorkSelectionRecord).filter_by(task_id=task_id)
        if snapshot_id:
            query = query.filter_by(snapshot_id=snapshot_id)
        record = query.order_by(RelatedWorkSelectionRecord.created_at.desc()).first()
        return _selection_to_dict(record) if record else None
    finally:
        db.close()


def create_selection_job(payload: dict) -> dict:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSelectionRecord).filter_by(cache_key=payload["cache_key"]).first()
        if record is None:
            record = RelatedWorkSelectionRecord(id=payload["id"], cache_key=payload["cache_key"])
            db.add(record)
        record.task_id = payload["task_id"]
        record.snapshot_id = payload["snapshot_id"]
        record.status = "pending"
        record.provider_id = payload["provider_id"]
        record.model_name = payload["model_name"]
        record.prompt_version = payload["prompt_version"]
        record.strategy_version = payload["strategy_version"]
        record.candidate_count = int(payload.get("candidate_count") or 0)
        record.selected_count = 0
        record.metadata_json = json.dumps(payload.get("metadata") or {}, ensure_ascii=False)
        record.selections_json = "[]"
        record.failure_reason = ""
        record.error = ""
        record.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        record.started_at = None
        record.completed_at = None
        db.commit()
        db.refresh(record)
        return _selection_to_dict(record)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def mark_selection_running(selection_id: str) -> dict | None:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSelectionRecord).filter_by(id=selection_id).first()
        if record is None:
            return None
        record.status = "running"
        record.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(record)
        return _selection_to_dict(record)
    finally:
        db.close()


def finish_selection_job(
    selection_id: str,
    *,
    status: str,
    selections: list[dict] | None = None,
    metadata: dict | None = None,
    failure_reason: str = "",
    error: str = "",
) -> dict | None:
    db = next(get_db())
    try:
        record = db.query(RelatedWorkSelectionRecord).filter_by(id=selection_id).first()
        if record is None:
            return None
        record.status = status
        if selections is not None:
            record.selections_json = json.dumps(selections, ensure_ascii=False)
            record.selected_count = len(selections)
        if metadata is not None:
            record.metadata_json = json.dumps(metadata, ensure_ascii=False)
        record.failure_reason = str(failure_reason or "")
        record.error = str(error or "")[:2000]
        record.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(record)
        return _selection_to_dict(record)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def invalidate_related_work(task_id: str) -> dict:
    """Delete only derived snapshots/selections; source PDF and user data are untouched."""
    db = next(get_db())
    try:
        selections = db.query(RelatedWorkSelectionRecord).filter_by(task_id=task_id).delete(
            synchronize_session=False
        )
        snapshots = db.query(RelatedWorkSnapshotRecord).filter_by(task_id=task_id).delete(
            synchronize_session=False
        )
        db.commit()
        return {"related_work_snapshots": snapshots, "smart_selections": selections}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _selection_to_dict(record: RelatedWorkSelectionRecord) -> dict:
    def iso(value) -> str:
        return value.replace(tzinfo=timezone.utc).isoformat() if value else ""

    return {
        "id": record.id,
        "task_id": record.task_id,
        "snapshot_id": record.snapshot_id,
        "cache_key": record.cache_key,
        "status": record.status,
        "provider_id": record.provider_id,
        "model_name": record.model_name,
        "prompt_version": record.prompt_version,
        "strategy_version": record.strategy_version,
        "candidate_count": record.candidate_count,
        "selected_count": record.selected_count,
        "metadata": json.loads(record.metadata_json or "{}"),
        "selections": json.loads(record.selections_json or "[]"),
        "failure_reason": record.failure_reason,
        "error": record.error,
        "created_at": iso(record.created_at),
        "started_at": iso(record.started_at),
        "completed_at": iso(record.completed_at),
    }
