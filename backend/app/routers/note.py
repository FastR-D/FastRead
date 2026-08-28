from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.core.settings import get_settings
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.paper_ingest_service import PaperIngestService
from app.services.paper_index_service import PaperIndexService
from app.services.paper_search_service import PaperSearchService
from app.services.paper_task_service import PaperTaskService
from app.services.reading_report_service import ReadingReportService
from app.services.related_work_service import RelatedWorkService
from app.services.venue_catalog import allowed_venue_catalog
from app.utils.local_access import require_local_request
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R
from app.validators.task_id_validator import CanonicalTaskId


logger = get_logger(__name__)
router = APIRouter(dependencies=[Depends(require_local_request)])


class CollectionUpdateRequest(BaseModel):
    collection_folder: Optional[str] = None
    collection_tags: Optional[list[str] | str] = None
    collection_note: Optional[str] = None


class ReadingReportRequest(BaseModel):
    task_id: CanonicalTaskId
    provider_id: str
    model_name: str
    force: bool = False


class PersonalSummaryRequest(BaseModel):
    summary: str = ""

    @field_validator("summary")
    @classmethod
    def validate_summary_length(cls, value: str) -> str:
        if len(value or "") > 300:
            raise ValueError("个人总结不能超过 300 字")
        return value


class PaperSearchRequest(BaseModel):
    query: str
    tracks: list[str] = Field(default_factory=lambda: ["security", "systems", "ai"])
    venue_ids: list[str] = Field(default_factory=list)
    limit: int = 20
    include_unconfirmed: bool = True
    refresh: bool = True
    include_arxiv: bool = True
    include_scholar: bool = True

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("检索关键词不能为空")
        return cleaned[:300]

    @field_validator("tracks")
    @classmethod
    def validate_tracks(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(str(item).strip().lower() for item in value if str(item).strip()))
        if not cleaned or any(item not in {"security", "systems", "ai"} for item in cleaned):
            raise ValueError("检索方向仅支持 security、systems、ai")
        return cleaned

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        return max(1, min(int(value or 20), 50))


class PaperIndexRebuildRequest(BaseModel):
    provider_id: str = ""
    model_name: str = ""
    use_ai: bool = True


class PaperUrlRequest(BaseModel):
    url: str
    provider_id: str = ""
    model_name: str = ""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    venue: str = ""
    year: Optional[int] = None
    doi: str = ""

    @field_validator("url")
    @classmethod
    def validate_paper_url(cls, value: str) -> str:
        parsed = urlparse(value or "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("论文地址必须是有效的 http/https URL")
        return value


class RelatedWorkRequest(BaseModel):
    force: bool = False
    limit: int = 120

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        return max(1, min(int(value or 120), 200))


settings = get_settings()
UPLOAD_DIR = settings.uploads_dir
MAX_UPLOAD_BYTES = settings.max_upload_bytes
IO_CHUNK_SIZE = 1024 * 1024
ARTIFACTS = PaperArtifactRepository(settings.paper_output_dir)
PAPER_TASKS = PaperTaskService(ARTIFACTS)
READING_REPORTS = ReadingReportService(ARTIFACTS)
PAPERS = PaperIngestService(ARTIFACTS)
PAPER_SEARCH = PaperSearchService()
PAPER_INDEX = PaperIndexService(PAPER_SEARCH, ARTIFACTS)
RELATED_WORK = RelatedWorkService(ARTIFACTS, PAPER_SEARCH)


@router.get("/tasks")
def list_paper_tasks():
    return R.success(PAPER_TASKS.list_tasks())


@router.get("/task_status/{task_id}")
def get_paper_task_status(task_id: CanonicalTaskId):
    return R.success(PAPER_TASKS.get_task_status(task_id))


@router.delete("/papers/{task_id}")
def delete_paper(task_id: CanonicalTaskId):
    deleted = PAPER_TASKS.delete_task(task_id)
    if not deleted:
        return R.error(msg="论文任务不存在", code=404)
    return R.success({"task_id": task_id}, msg="删除成功")


@router.put("/papers/{task_id}/collection")
def update_paper_collection(task_id: CanonicalTaskId, data: CollectionUpdateRequest):
    updated = PAPER_TASKS.update_collection(
        task_id=task_id,
        collection_folder=data.collection_folder,
        collection_tags=data.collection_tags,
        collection_note=data.collection_note,
    )
    if not updated:
        return R.error(msg="论文任务不存在", code=404)
    return R.success(updated)


@router.post("/papers/search")
def search_papers(data: PaperSearchRequest):
    try:
        return R.success(
            PAPER_SEARCH.search(
                query=data.query,
                tracks=tuple(data.tracks),
                venue_ids=tuple(data.venue_ids),
                limit=data.limit,
                include_unconfirmed=data.include_unconfirmed,
                refresh=data.refresh,
                include_arxiv=data.include_arxiv,
                include_scholar=data.include_scholar,
            )
        )
    except Exception as exc:
        logger.error(f"论文检索失败 (query={data.query}): {exc}", exc_info=True)
        return R.error(msg=f"论文检索失败: {exc}")


@router.get("/papers/search/venues")
def list_search_venues():
    return R.success(
        {
            "venues": [
                {
                    "id": venue_id,
                    "name": metadata["name"],
                    "short_name": metadata["short_name"],
                    "track": metadata["track"],
                }
                for venue_id, metadata in allowed_venue_catalog().items()
            ]
        }
    )


@router.post("/papers/search/index/rebuild")
def rebuild_paper_index(data: PaperIndexRebuildRequest):
    try:
        return R.success(
            PAPER_INDEX.rebuild(
                provider_id=data.provider_id,
                model_name=data.model_name,
                use_ai=data.use_ai,
            )
        )
    except ValueError as exc:
        return R.error(msg=str(exc), code=400)
    except Exception as exc:
        logger.error(f"离线论文索引重建失败: {exc}", exc_info=True)
        return R.error(msg=f"离线论文索引重建失败: {exc}")


@router.get("/papers/search/index/status")
def get_paper_index_status(include_records: bool = False):
    return R.success(PAPER_INDEX.latest_status(include_records=include_records))


@router.post("/papers/{task_id}/related-work")
def generate_related_work(task_id: CanonicalTaskId, data: RelatedWorkRequest | None = None):
    try:
        request = data or RelatedWorkRequest()
        return R.success(RELATED_WORK.generate(task_id, force=request.force, limit=request.limit))
    except ValueError as exc:
        return R.error(msg=str(exc), code=400)
    except Exception as exc:
        logger.error(f"近邻论文检索失败 (task_id={task_id}): {exc}", exc_info=True)
        return R.error(msg=f"近邻论文检索失败: {exc}")


@router.get("/papers/{task_id}/related-work")
def get_related_work(task_id: CanonicalTaskId):
    snapshot = RELATED_WORK.get(task_id)
    return R.success(snapshot)


@router.post("/reading_reports")
def generate_reading_report(data: ReadingReportRequest):
    try:
        report = READING_REPORTS.generate(
            task_id=data.task_id,
            provider_id=data.provider_id,
            model_name=data.model_name,
            force=data.force,
        )
        return R.success({"task_id": data.task_id, "reading_report": report})
    except ValueError as exc:
        return R.error(msg=str(exc), code=400)
    except Exception as exc:
        logger.error(f"生成学术阅读报告失败 (task_id={data.task_id}): {exc}", exc_info=True)
        return R.error(msg=f"生成学术阅读报告失败: {exc}")


@router.put("/reading_reports/{task_id}/personal_summary")
def save_personal_summary(task_id: CanonicalTaskId, data: PersonalSummaryRequest):
    try:
        summary = READING_REPORTS.save_personal_summary(task_id=task_id, summary=data.summary)
        return R.success({"task_id": task_id, "personal_summary": summary})
    except ValueError as exc:
        return R.error(msg=str(exc), code=400)


@router.post("/papers/from_url")
def ingest_paper_url(data: PaperUrlRequest):
    try:
        created = PAPERS.ingest_url(
            url=data.url,
            provider_id=data.provider_id,
            model_name=data.model_name,
            overrides={
                "title": data.title,
                "authors": data.authors,
                "venue": data.venue,
                "year": data.year,
                "doi": data.doi,
            },
        )
        return R.success(PAPER_TASKS.get_task_status(created["task_id"]))
    except ValueError as exc:
        return R.error(msg=str(exc), code=400)
    except Exception as exc:
        logger.error(f"导入论文 URL 失败: {exc}", exc_info=True)
        return R.error(msg=f"导入论文 URL 失败: {exc}")


@router.post("/papers/upload")
async def ingest_paper_upload(
    _: None = Depends(require_local_request),
    file: UploadFile = File(...),
    provider_id: str = Form(""),
    model_name: str = Form(""),
    source_url: str = Form(""),
    venue: str = Form(""),
    doi: str = Form(""),
    year: str = Form(""),
):
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="论文导入仅支持 PDF")
    body = bytearray()
    while True:
        chunk = await file.read(IO_CHUNK_SIZE)
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="PDF 文件过大")

    safe_name = f"{uuid.uuid4().hex}.pdf"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_pdf = UPLOAD_DIR / safe_name
    temporary = stored_pdf.with_suffix(".pdf.part")
    try:
        temporary.write_bytes(body)
        os.replace(temporary, stored_pdf)
        created = PAPERS.ingest_pdf(
            content=bytes(body),
            filename=file.filename or "paper.pdf",
            source_url=source_url or f"{settings.uploads_path.rstrip('/')}/{safe_name}",
            provider_id=provider_id,
            model_name=model_name,
            overrides={"venue": venue, "doi": doi, "year": year},
        )
        return R.success(PAPER_TASKS.get_task_status(created["task_id"]))
    except ValueError as exc:
        if temporary.exists():
            temporary.unlink()
        if stored_pdf.exists():
            stored_pdf.unlink()
        return R.error(msg=str(exc), code=400)
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        if stored_pdf.exists():
            stored_pdf.unlink()
        logger.error(f"导入 PDF 失败: {exc}", exc_info=True)
        return R.error(msg=f"导入 PDF 失败: {exc}")
