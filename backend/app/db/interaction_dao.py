from __future__ import annotations

import hashlib
import json
import uuid

from app.db.engine import get_db
from app.db.models.paper_tasks import InteractionReceipt


def scoped_idempotency_key(account_id: str, operation: str, key: str) -> str:
    return hashlib.sha256(f"{account_id}\0{operation}\0{key}".encode("utf-8")).hexdigest()


def get_receipt(account_id: str, operation: str, key: str) -> dict | None:
    db = next(get_db())
    try:
        record = db.query(InteractionReceipt).filter_by(
            idempotency_key=scoped_idempotency_key(account_id, operation, key)
        ).first()
        if not record:
            return None
        return {
            "request_hash": record.request_hash,
            "response": json.loads(record.response_json or "{}"),
        }
    finally:
        db.close()


def save_receipt(account_id: str, operation: str, key: str, request_hash: str, response: dict) -> None:
    db = next(get_db())
    try:
        scoped = scoped_idempotency_key(account_id, operation, key)
        record = db.query(InteractionReceipt).filter_by(idempotency_key=scoped).first()
        if record is None:
            record = InteractionReceipt(
                id=uuid.uuid4().hex,
                account_id=account_id,
                operation=operation,
                idempotency_key=scoped,
            )
            db.add(record)
        record.request_hash = request_hash
        record.response_json = json.dumps(response, ensure_ascii=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
