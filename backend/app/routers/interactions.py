from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db.interaction_dao import get_receipt, save_receipt
from app.db.paper_task_dao import list_paper_tasks
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.auth import AccountPrincipal, current_account
from app.services.metadata_migration_service import MetadataMigrationService
from app.services.paper_ingest_service import PaperIngestService
from app.services.paper_task_service import PaperTaskService
from app.utils.response import ResponseWrapper as R


router = APIRouter(prefix="/v1/interactions")
ARTIFACTS = PaperArtifactRepository()
PAPERS = PaperIngestService(ARTIFACTS)
PAPER_TASKS = PaperTaskService(ARTIFACTS)


class PushRequest(BaseModel):
    paper_url: str
    tags: list[str] = Field(default_factory=list)

    @field_validator("paper_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parsed = urlparse(str(value or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("paper_url must be an http/https URL")
        return parsed.geturl()

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(str(tag).strip() for tag in value if str(tag).strip()))[:32]


class GetRequest(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=32)
    limit: int = Field(default=20, ge=1, le=100)


class MigrationRequest(BaseModel):
    dry_run: bool = True
    task_ids: list[str] = Field(default_factory=list)


def _request_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@router.post("/push")
def push_paper(
    data: PushRequest,
    account: AccountPrincipal = Depends(current_account),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
):
    request_payload = data.model_dump(mode="json")
    digest = _request_hash(request_payload)
    prior = get_receipt(account.account_id, "push", idempotency_key)
    if prior:
        if prior["request_hash"] != digest:
            raise HTTPException(status_code=409, detail="idempotency key was already used for another request")
        return R.success({**prior["response"], "idempotent_replay": True})
    created = PAPERS.ingest_url(url=data.paper_url)
    task_id = created["task_id"]
    if data.tags:
        PAPER_TASKS.update_collection(task_id=task_id, collection_tags=data.tags)
    response = {
        "contract_version": "v1",
        "task_id": task_id,
        "status": "imported",
        "open_path": f"/workspace?task_id={task_id}",
        "account_id": account.account_id,
        "idempotent_replay": False,
    }
    save_receipt(account.account_id, "push", idempotency_key, digest, response)
    return R.success(response)


@router.post("/get")
def get_papers(data: GetRequest, account: AccountPrincipal = Depends(current_account)):
    requested = {tag.casefold() for tag in data.tags}
    matches = []
    for task in list_paper_tasks():
        tags = {str(tag).casefold() for tag in task.get("collection_tags") or []}
        overlap = sorted(requested & tags)
        if not overlap:
            continue
        matches.append(
            {
                "task_id": task["task_id"],
                "title": task["title"],
                "authors": task["authors"],
                "year": task["year"],
                "tags": task.get("collection_tags") or [],
                "matched_tags": overlap,
                "open_path": f"/workspace?task_id={task['task_id']}",
            }
        )
    matches.sort(key=lambda item: (-len(item["matched_tags"]), item["title"].casefold()))
    return R.success(
        {"contract_version": "v1", "account_id": account.account_id, "papers": matches[: data.limit]}
    )


@router.post("/metadata-migrations")
def migrate_metadata(data: MigrationRequest, _account: AccountPrincipal = Depends(current_account)):
    return R.success(
        MetadataMigrationService(ARTIFACTS).run(
            dry_run=data.dry_run,
            task_ids=set(data.task_ids) if data.task_ids else None,
        )
    )
