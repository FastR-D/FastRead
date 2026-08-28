from __future__ import annotations

import json
from typing import Any

from app.db.engine import get_db
from app.db.models.paper_tasks import PaperTask
from app.utils.collections import (
    DEFAULT_COLLECTION_FOLDER,
    normalize_collection_folder,
    require_collection_folder,
)


def _loads_list(value: str | None) -> list:
    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _to_dict(task: PaperTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "task_id": task.task_id,
        "title": task.title,
        "authors": _loads_list(task.authors_json),
        "year": task.year,
        "venue": {
            "id": task.venue_id,
            "name": task.venue_name,
            "short_name": task.venue_name,
            "track": task.venue_track,
        },
        "identity_status": task.identity_status,
        "doi": task.doi,
        "source_url": task.source_url,
        "resolved_source_url": task.resolved_source_url,
        "pdf_url": task.pdf_url,
        "upload_filename": task.upload_filename,
        "content_hash": task.content_hash,
        "report_version": task.report_version,
        "collection_folder": task.collection_folder,
        "collection_tags": _loads_list(task.collection_tags_json),
        "collection_note": task.collection_note,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def upsert_paper_task(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required")
    db = next(get_db())
    try:
        task = db.query(PaperTask).filter_by(task_id=task_id).first()
        if task is None:
            task = PaperTask(task_id=task_id, title=str(payload.get("title") or "未命名论文"))
            db.add(task)
        task.title = str(payload.get("title") or task.title or "未命名论文")
        task.authors_json = json.dumps(payload.get("authors") or [], ensure_ascii=False)
        task.year = payload.get("year")
        venue = payload.get("venue") or {}
        task.venue_id = str(venue.get("id") or "")
        task.venue_name = str(venue.get("short_name") or venue.get("name") or venue.get("raw") or "")
        task.venue_track = str(venue.get("track") or "")
        task.identity_status = str(payload.get("identity_status") or "incomplete")
        task.doi = str(payload.get("doi") or "")
        task.source_url = str(payload.get("source_url") or "")
        task.resolved_source_url = str(payload.get("resolved_source_url") or "")
        task.pdf_url = str(payload.get("pdf_url") or "")
        task.upload_filename = str(payload.get("upload_filename") or payload.get("filename") or "")
        task.content_hash = str(payload.get("content_hash") or "")
        task.report_version = str(payload.get("report_version") or "")
        task.collection_folder = (
            require_collection_folder(payload.get("collection_folder"))
            if payload.get("collection_folder")
            else DEFAULT_COLLECTION_FOLDER
        )
        task.collection_tags_json = json.dumps(payload.get("collection_tags") or [], ensure_ascii=False)
        task.collection_note = str(payload.get("collection_note") or "")
        db.commit()
        db.refresh(task)
        return _to_dict(task)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_paper_task(task_id: str) -> dict[str, Any] | None:
    db = next(get_db())
    try:
        task = db.query(PaperTask).filter_by(task_id=task_id).first()
        return _to_dict(task) if task else None
    finally:
        db.close()


def list_paper_tasks() -> list[dict[str, Any]]:
    db = next(get_db())
    try:
        tasks = db.query(PaperTask).order_by(PaperTask.updated_at.desc(), PaperTask.created_at.desc()).all()
        return [_to_dict(task) for task in tasks]
    finally:
        db.close()


def update_paper_collection(
    task_id: str,
    *,
    collection_folder: str | None = None,
    collection_tags: list[str] | str | None = None,
    collection_note: str | None = None,
) -> dict[str, Any] | None:
    db = next(get_db())
    try:
        task = db.query(PaperTask).filter_by(task_id=task_id).first()
        if task is None:
            return None
        if collection_folder is not None:
            task.collection_folder = require_collection_folder(collection_folder)
        if collection_tags is not None:
            tags = collection_tags if isinstance(collection_tags, list) else [collection_tags]
            task.collection_tags_json = json.dumps(
                [str(tag).strip() for tag in tags if str(tag).strip()], ensure_ascii=False
            )
        if collection_note is not None:
            task.collection_note = collection_note
        db.commit()
        db.refresh(task)
        return _to_dict(task)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_paper_collection(
    collection_folder: str,
    *,
    replacement_folder: str = DEFAULT_COLLECTION_FOLDER,
) -> list[str]:
    folder = require_collection_folder(collection_folder)
    replacement = require_collection_folder(replacement_folder)
    db = next(get_db())
    try:
        folder_key = normalize_collection_folder(folder).casefold()
        tasks = [
            task
            for task in db.query(PaperTask).all()
            if normalize_collection_folder(task.collection_folder).casefold() == folder_key
        ]
        task_ids = [task.task_id for task in tasks]
        for task in tasks:
            task.collection_folder = replacement
        db.commit()
        return task_ids
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_paper_task(task_id: str) -> bool:
    db = next(get_db())
    try:
        task = db.query(PaperTask).filter_by(task_id=task_id).first()
        if task is None:
            return False
        db.delete(task)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
