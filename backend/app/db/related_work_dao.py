from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.engine import get_db
from app.db.models.paper_tasks import RelatedWorkSnapshotRecord


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
        "provider_status": json.loads(record.provider_status_json or "{}"),
        "search_backend": record.search_backend,
        "generated_at": record.generated_at.replace(tzinfo=timezone.utc).isoformat()
        if record.generated_at
        else "",
    }
