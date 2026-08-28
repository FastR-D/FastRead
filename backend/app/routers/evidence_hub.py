from __future__ import annotations

import json
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.settings import get_settings
from app.db.evidence_dao import EvidenceHubDAO
from app.services.candidate_inbox_service import CandidateInboxService, FastNewsCatalogService
from app.services.evidence_hub_service import EVIDENCE_ROLES, EvidenceHubService
from app.services.fastwrite_handoff_service import FastWriteHandoffService
from app.utils.local_access import require_local_request
from app.utils.response import ResponseWrapper as R
from app.validators.task_id_validator import CanonicalTaskId


router = APIRouter(dependencies=[Depends(require_local_request)])
DAO = EvidenceHubDAO()
HUB = EvidenceHubService(DAO)
CATALOG = FastNewsCatalogService()
INBOX = CandidateInboxService(DAO, CATALOG)
HANDOFFS = FastWriteHandoffService(DAO)


class AnnotationCreate(BaseModel):
    page: int = Field(ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    exact_quote: str = Field(min_length=1, max_length=20000)
    note: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def offsets_are_ordered(self):
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset 必须大于 start_offset")
        return self


class AnnotationPatch(BaseModel):
    page: int | None = Field(default=None, ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, gt=0)
    exact_quote: str | None = Field(default=None, min_length=1, max_length=20000)
    note: str | None = Field(default=None, max_length=10000)


class FastNewsImportRequest(BaseModel):
    catalog_ids: list[str] = Field(min_length=1, max_length=200)


class TopicCreate(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    scope_statement: str = Field(default="", max_length=20000)
    user_hypotheses: list[str] = Field(default_factory=list, max_length=200)


class TopicPatch(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=5000)
    scope_statement: str | None = Field(default=None, max_length=20000)
    user_hypotheses: list[str] | None = Field(default=None, max_length=200)


class EvidenceCreate(BaseModel):
    task_id: CanonicalTaskId
    page: int = Field(ge=1)
    exact_quote: str = Field(min_length=1, max_length=20000)
    user_note: str = Field(default="", max_length=10000)
    role: str = "other"

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in EVIDENCE_ROLES:
            raise ValueError("未知证据角色")
        return value


class EvidenceExtractionRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=200)
    model_name: str = Field(min_length=1, max_length=500)
    max_candidates: int = Field(default=120, ge=40, le=160)


class SynthesisRequest(BaseModel):
    proposed: dict | None = None
    provider_id: str = Field(default="", max_length=200)
    model_name: str = Field(default="", max_length=500)


class TopicChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class TopicAskRequest(BaseModel):
    question: str = Field(default="", max_length=10000)
    history: list[TopicChatMessage] = Field(default_factory=list, max_length=50)
    provider_id: str = Field(min_length=1, max_length=200)
    model_name: str = Field(min_length=1, max_length=500)
    mode: Literal["question", "summary"] = "question"

    @model_validator(mode="after")
    def question_required_for_question_mode(self):
        if self.mode == "question" and not self.question.strip():
            raise ValueError("问题不能为空")
        return self


class HandoffRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    task_id: CanonicalTaskId | None = None
    topic_id: str | None = None
    include_user_notes: bool = False

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.task_id) == bool(self.topic_id):
            raise ValueError("必须且只能选择一篇论文或一个专题")
        return self


def _error(exc: Exception):
    if isinstance(exc, LookupError):
        return R.error(msg=str(exc), code=404)
    return R.error(msg=str(exc), code=400)


@router.get("/papers/{task_id}/annotations")
def list_annotations(task_id: CanonicalTaskId):
    try:
        return R.success(HUB.list_annotations(task_id))
    except Exception as exc:
        return _error(exc)


@router.post("/papers/{task_id}/annotations")
def create_annotation(task_id: CanonicalTaskId, data: AnnotationCreate):
    try:
        return R.success(HUB.create_annotation(task_id, data.model_dump()), status_code=201)
    except Exception as exc:
        return _error(exc)


@router.patch("/papers/{task_id}/annotations/{annotation_id}")
def update_annotation(task_id: CanonicalTaskId, annotation_id: str, data: AnnotationPatch):
    try:
        return R.success(HUB.update_annotation(task_id, annotation_id, data.model_dump(exclude_unset=True)))
    except Exception as exc:
        return _error(exc)


@router.delete("/papers/{task_id}/annotations/{annotation_id}")
def delete_annotation(task_id: CanonicalTaskId, annotation_id: str):
    try:
        HUB.delete_annotation(task_id, annotation_id)
        return R.success({"deleted": True})
    except Exception as exc:
        return _error(exc)


@router.get("/integrations/fastnews/catalog")
def fastnews_catalog(
    q: str = "",
    venue: str = "",
    year: int | None = None,
    category: str = "",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    refresh: bool = False,
):
    try:
        catalog = CATALOG.catalog(force=refresh)
        entries = catalog.get("entries") or []
        if q:
            needle = q.casefold()
            entries = [item for item in entries if needle in f"{item.get('title')} {item.get('abstract')} {' '.join(item.get('authors') or [])}".casefold()]
        if venue:
            entries = [item for item in entries if venue.casefold() in str(item.get("venue") or "").casefold()]
        if year is not None:
            entries = [item for item in entries if item.get("year") == year]
        if category:
            entries = [item for item in entries if category.casefold() in json.dumps(item.get("raw") or {}, ensure_ascii=False).casefold()]
        return R.success({
            **{key: value for key, value in catalog.items() if key != "entries"},
            "total": len(entries),
            "offset": offset,
            "entries": entries[offset:offset + limit],
        })
    except Exception as exc:
        return _error(exc)


@router.post("/integrations/imports/fastnews")
def import_fastnews(data: FastNewsImportRequest):
    try:
        return R.success(INBOX.import_fastnews(data.catalog_ids), status_code=201)
    except Exception as exc:
        return _error(exc)


@router.post("/integrations/imports/fastinsight")
async def import_fastinsight(request: Request):
    settings = get_settings()
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.fastinsight_max_bytes:
        raise HTTPException(status_code=413, detail="FastInsight JSON 超过 1 MiB 限制")
    content_type = request.headers.get("content-type", "").lower()
    raw = b""
    try:
        if content_type.startswith("multipart/form-data") or content_type.startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            file = form.get("file")
            if isinstance(file, StarletteUploadFile):
                raw = await file.read(settings.fastinsight_max_bytes + 1)
            else:
                raw = str(form.get("payload") or form.get("json") or "").encode("utf-8")
        else:
            raw = await request.body()
        if len(raw) > settings.fastinsight_max_bytes:
            raise HTTPException(status_code=413, detail="FastInsight JSON 超过 1 MiB 限制")
        payload = json.loads(raw.decode("utf-8-sig"))
        return R.success(INBOX.import_fastinsight(payload), status_code=201)
    except HTTPException:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return R.error(msg=f"FastInsight JSON 无法解析：{exc}", code=400)
    except Exception as exc:
        return _error(exc)


@router.get("/integrations/imports")
def list_imports(
    producer: str = "",
    venue: str = "",
    year: int | None = None,
    category: str = "",
    status: str = "",
):
    return R.success(DAO.list_candidates({
        "producer": producer,
        "venue": venue,
        "year": year,
        "category": category,
        "status": status,
    }))


@router.post("/integrations/imports/{candidate_id}/confirm")
def confirm_import(candidate_id: str):
    try:
        return R.success(INBOX.confirm(candidate_id))
    except Exception as exc:
        return _error(exc)


@router.delete("/integrations/imports/{candidate_id}")
def delete_import(candidate_id: str):
    if not DAO.delete_candidate(candidate_id):
        return R.error(msg="候选不存在", code=404)
    return R.success({"deleted": True})


@router.post("/research_topics")
def create_topic(data: TopicCreate):
    try:
        return R.success(HUB.create_topic(data.model_dump()), status_code=201)
    except Exception as exc:
        return _error(exc)


@router.get("/research_topics")
def list_topics():
    return R.success(DAO.list_topics())


@router.get("/research_topics/{topic_id}")
def get_topic(topic_id: str):
    try:
        return R.success(HUB.get_topic(topic_id))
    except Exception as exc:
        return _error(exc)


@router.patch("/research_topics/{topic_id}")
def update_topic(topic_id: str, data: TopicPatch):
    try:
        return R.success(HUB.update_topic(topic_id, data.model_dump(exclude_unset=True)))
    except Exception as exc:
        return _error(exc)


@router.delete("/research_topics/{topic_id}")
def delete_topic(topic_id: str):
    try:
        HUB.delete_topic(topic_id)
        return R.success({"deleted": True})
    except Exception as exc:
        return _error(exc)


@router.post("/research_topics/{topic_id}/papers/{task_id}")
def add_topic_paper(topic_id: str, task_id: CanonicalTaskId):
    try:
        return R.success(HUB.add_topic_paper(topic_id, task_id), status_code=201)
    except Exception as exc:
        return _error(exc)


@router.delete("/research_topics/{topic_id}/papers/{task_id}")
def remove_topic_paper(topic_id: str, task_id: CanonicalTaskId):
    try:
        HUB.remove_topic_paper(topic_id, task_id)
        return R.success({"deleted": True})
    except Exception as exc:
        return _error(exc)


@router.post("/research_topics/{topic_id}/evidence")
def add_topic_evidence(topic_id: str, data: EvidenceCreate):
    try:
        return R.success(HUB.add_evidence(topic_id, data.model_dump()), status_code=201)
    except Exception as exc:
        return _error(exc)


@router.delete("/research_topics/{topic_id}/evidence/{evidence_id}")
def delete_topic_evidence(topic_id: str, evidence_id: str):
    try:
        HUB.delete_evidence(topic_id, evidence_id)
        return R.success({"deleted": True})
    except Exception as exc:
        return _error(exc)


@router.post("/research_topics/{topic_id}/evidence/extract")
def extract_topic_evidence(topic_id: str, data: EvidenceExtractionRequest):
    try:
        return R.success(HUB.extract_topic_evidence(topic_id, data.model_dump()))
    except Exception as exc:
        return _error(exc)


@router.post("/research_topics/{topic_id}/syntheses")
def create_synthesis(topic_id: str, data: SynthesisRequest | None = None):
    try:
        return R.success(HUB.create_synthesis(topic_id, (data or SynthesisRequest()).model_dump()), status_code=201)
    except Exception as exc:
        return _error(exc)


@router.get("/research_topics/{topic_id}/syntheses")
def list_syntheses(topic_id: str):
    try:
        return R.success(HUB.list_syntheses(topic_id))
    except Exception as exc:
        return _error(exc)


@router.post("/research_topics/{topic_id}/ask")
def ask_topic(topic_id: str, data: TopicAskRequest):
    try:
        return R.success(HUB.ask_topic(topic_id, data.model_dump()))
    except Exception as exc:
        return _error(exc)


@router.get("/integrations/fastwrite/status")
def fastwrite_status():
    return R.success(HANDOFFS.status())


@router.get("/integrations/fastwrite/projects")
def fastwrite_projects():
    try:
        return R.success(HANDOFFS.projects())
    except Exception as exc:
        return _error(exc)


@router.post("/integrations/fastwrite/handoffs")
def create_handoff(data: HandoffRequest):
    try:
        return R.success(HANDOFFS.create(data.model_dump()), status_code=201)
    except Exception as exc:
        return _error(exc)


@router.get("/integrations/fastwrite/handoffs")
def list_handoffs():
    return R.success(DAO.list_handoffs())


@router.post("/integrations/fastwrite/handoffs/{handoff_id}/retry")
def retry_handoff(handoff_id: str):
    try:
        return R.success(HANDOFFS.retry(handoff_id))
    except Exception as exc:
        return _error(exc)


@router.get("/integrations/fastwrite/handoffs/{handoff_id}/download")
def download_handoff(handoff_id: str, format: Literal["zip", "markdown", "bibtex", "json"] = "zip"):
    try:
        receipt = DAO.get_handoff(handoff_id)
        if not receipt:
            raise LookupError("交接记录不存在")
        bundle = HANDOFFS.bundles._load_bundle(receipt["bundle_id"])
        if format == "zip":
            bundle_id, content = HANDOFFS.download(handoff_id)
            return StreamingResponse(
                BytesIO(content),
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="fastread-{bundle_id}.zip"'},
            )
        name, media_type = {
            "markdown": ("evidence.md", "text/markdown; charset=utf-8"),
            "bibtex": ("references.bib", "application/x-bibtex; charset=utf-8"),
            "json": ("citations.json", "application/json; charset=utf-8"),
        }[format]
        return Response(
            content=bundle["contents"][name],
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    except Exception as exc:
        if isinstance(exc, LookupError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
