from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.engine import get_db
from app.db.models.paper_tasks import PaperIndexJob, PaperKeywordRecord


def _job_payload(job: PaperIndexJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "job_id": job.id,
        "status": job.status,
        "provider_id": job.provider_id,
        "model_name": job.model_name,
        "prompt_version": job.prompt_version,
        "strategy_version": job.strategy_version,
        "corpus_count": job.corpus_count,
        "ai_keyword_count": job.ai_keyword_count,
        "fallback_count": job.fallback_count,
        "fallback_reasons": json.loads(job.fallback_reasons_json or "{}"),
        "local_index_count": job.local_index_count,
        "elasticsearch_index_count": job.elasticsearch_index_count,
        "search_backend": job.search_backend,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else "",
        "completed_at": job.completed_at.isoformat() if job.completed_at else "",
    }


def create_index_job(
    *,
    job_id: str,
    provider_id: str,
    model_name: str,
    prompt_version: str,
    strategy_version: str,
) -> dict:
    db = next(get_db())
    try:
        job = PaperIndexJob(
            id=job_id,
            status="running",
            provider_id=provider_id,
            model_name=model_name,
            prompt_version=prompt_version,
            strategy_version=strategy_version,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return _job_payload(job) or {}
    finally:
        db.close()


def save_keyword_records(job_id: str, records: list[dict]) -> None:
    db = next(get_db())
    try:
        for record in records:
            db.add(
                PaperKeywordRecord(
                    id=f"{job_id}:{record['paper_id']}",
                    job_id=job_id,
                    paper_id=record["paper_id"],
                    task_id=record.get("task_id") or "",
                    title=record.get("title") or "",
                    abstract_hash=record.get("abstract_hash") or "",
                    keywords_json=json.dumps(record.get("keywords") or [], ensure_ascii=False),
                    execution_status=record.get("execution_status") or "fallback",
                    fallback_reason=record.get("fallback_reason") or "",
                    provider_id=record.get("provider_id") or "",
                    model_name=record.get("model_name") or "",
                    prompt_version=record["prompt_version"],
                    strategy_version=record["strategy_version"],
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def finish_index_job(job_id: str, **values) -> dict:
    db = next(get_db())
    try:
        job = db.query(PaperIndexJob).filter_by(id=job_id).one()
        for key, value in values.items():
            if key == "fallback_reasons":
                job.fallback_reasons_json = json.dumps(value or {}, ensure_ascii=False)
            elif hasattr(job, key):
                setattr(job, key, value)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        return _job_payload(job) or {}
    finally:
        db.close()


def latest_index_job() -> dict | None:
    db = next(get_db())
    try:
        job = db.query(PaperIndexJob).order_by(PaperIndexJob.started_at.desc()).first()
        return _job_payload(job)
    finally:
        db.close()


def list_keyword_records(job_id: str) -> list[dict]:
    db = next(get_db())
    try:
        rows = (
            db.query(PaperKeywordRecord)
            .filter_by(job_id=job_id)
            .order_by(PaperKeywordRecord.paper_id)
            .all()
        )
        return [
            {
                "paper_id": row.paper_id,
                "task_id": row.task_id,
                "title": row.title,
                "abstract_hash": row.abstract_hash,
                "keywords": json.loads(row.keywords_json or "[]"),
                "execution_status": row.execution_status,
                "fallback_reason": row.fallback_reason,
                "provider_id": row.provider_id,
                "model_name": row.model_name,
                "prompt_version": row.prompt_version,
                "strategy_version": row.strategy_version,
            }
            for row in rows
        ]
    finally:
        db.close()
