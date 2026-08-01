# app/routers/note.py
import ipaddress
import os
import socket
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel, field_validator, model_validator

from app.core.settings import get_settings
from app.enmus.exception import NoteErrorEnum
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.note import logger
from app.utils.local_access import require_local_request
from app.services.note_task_service import NoteTaskService
from app.services.paper_ingest_service import PaperIngestService
from app.services.reading_report_service import ReadingReportService
from app.utils.response import ResponseWrapper as R
from app.validators.video_url_validator import SUPPORTED_PLATFORMS, is_supported_video_url
from fastapi import Request
from fastapi.responses import Response
import httpx

# from app.services.downloader import download_raw_audio
# from app.services.whisperer import transcribe_audio

router = APIRouter()


class RecordRequest(BaseModel):
    task_id: Optional[str] = None
    video_id: Optional[str] = None
    platform: str = "douyin"


class CollectionUpdateRequest(BaseModel):
    task_id: str
    collection_folder: Optional[str] = None
    collection_tags: Optional[list[str] | str] = None
    collection_note: Optional[str] = None


class OnlineVerificationRequest(BaseModel):
    task_id: str
    max_claims: int = 50
    model_name: Optional[str] = None
    provider_id: Optional[str] = None


class VerificationTaskRequest(BaseModel):
    goal: str = "verify"
    input_mode: str = "text"
    text: Optional[str] = ""
    url: Optional[str] = ""
    task_id: Optional[str] = None
    max_claims: int = 50
    verification_depth: str = "deep"
    source_policy: str = "authoritative"
    model_name: Optional[str] = None
    provider_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_verification_input(self):
        if not (self.text or self.url or self.task_id):
            raise ValueError("请提供待核实文本、URL 或已有任务 ID")
        self.max_claims = max(1, min(int(self.max_claims or 50), 50))
        self.goal = "verify"
        self.verification_depth = self.verification_depth or "deep"
        self.source_policy = self.source_policy or "authoritative"
        return self


class VerificationRerunRequest(BaseModel):
    retry_failed_only: bool = True


class ReadingReportRequest(BaseModel):
    task_id: str
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


class PaperUrlRequest(BaseModel):
    url: str
    provider_id: str = ""
    model_name: str = ""
    title: str = ""
    authors: list[str] = []
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


class VideoRequest(BaseModel):
    video_url: str
    platform: str = "douyin"
    quality: DownloadQuality
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    model_name: str
    provider_id: str
    task_id: Optional[str] = None
    format: Optional[list] = []
    style: str = None
    extras: Optional[str]=None
    collection_folder: Optional[str] = None
    collection_tags: Optional[list[str] | str] = None
    collection_note: Optional[str] = None
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []
    # 客户端（如浏览器插件）已经在用户浏览器里抓到字幕，直接传给后端复用，
    # 跳过 download_subtitles 和音频转写。形如：
    #   {"language": "zh", "full_text": "...", "segments": [{"start","end","text"}, ...]}
    prefetched_transcript: Optional[dict] = None

    @field_validator("platform")
    def validate_platform(cls, v):
        if v not in SUPPORTED_PLATFORMS:
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message="当前仅支持抖音精选、B站、快手视频")
        return v

    @model_validator(mode="after")
    def validate_supported_url(self):
        if not is_supported_video_url(str(self.video_url), self.platform):
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message="请输入所选平台的视频链接")
        return self


settings = get_settings()
UPLOAD_DIR = settings.uploads_dir
UPLOADS_PATH = settings.uploads_path
MAX_UPLOAD_BYTES = settings.max_upload_bytes
MAX_IMAGE_PROXY_BYTES = settings.max_image_proxy_bytes
IO_CHUNK_SIZE = 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".txt", ".md", ".pdf",
}
ALLOWED_IMAGE_PROXY_HOSTS = settings.image_proxy_allowed_hosts
ARTIFACTS = NoteArtifactRepository(settings.note_output_dir)
NOTE_TASKS = NoteTaskService(ARTIFACTS)
READING_REPORTS = ReadingReportService(ARTIFACTS)
PAPERS = PaperIngestService(ARTIFACTS)


def _safe_upload_extension(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    return ext


def _assert_content_length_within_limit(headers, max_bytes: int) -> None:
    content_length = headers.get("Content-Length")
    if not content_length:
        return
    try:
        length = int(content_length)
    except ValueError:
        return
    if length > max_bytes:
        raise HTTPException(status_code=413, detail="文件过大")


def _assert_public_image_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="图片地址必须是 http/https URL")

    host = parsed.hostname.lower()
    if ALLOWED_IMAGE_PROXY_HOSTS and host not in ALLOWED_IMAGE_PROXY_HOSTS:
        raise HTTPException(status_code=403, detail="图片域名不在允许列表")

    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="图片域名无法解析")

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise HTTPException(status_code=403, detail="不允许代理内网或本机地址")

    return raw_url


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[]
                  ):

    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")
    NOTE_TASKS.execute_generation_task(
        task_id=task_id,
        video_url=video_url,
        platform=platform,
        quality=quality,
        link=link,
        screenshot=screenshot,
        model_name=model_name,
        provider_id=provider_id,
        formats=_format,
        style=style,
        extras=extras,
        video_understanding=video_understanding,
        video_interval=video_interval,
        grid_size=grid_size,
    )


@router.post('/delete_task')
def delete_task(data: RecordRequest):
    try:
        NOTE_TASKS.delete_task(task_id=data.task_id, video_id=data.video_id, platform=data.platform)
        return R.success(msg='删除成功')
    except Exception as e:
        return R.error(msg=e)


@router.post("/update_task_collection")
def update_collection(data: CollectionUpdateRequest):
    try:
        updated = NOTE_TASKS.update_collection(
            task_id=data.task_id,
            collection_folder=data.collection_folder,
            collection_tags=data.collection_tags,
            collection_note=data.collection_note,
        )
        if not updated:
            return R.error(msg="任务不存在", code=404)
        return R.success(data=updated)
    except Exception as e:
        return R.error(msg=e)


@router.post("/verify_task_online")
def verify_task_online(data: OnlineVerificationRequest):
    try:
        result = NOTE_TASKS.verify_task_online(
            task_id=data.task_id,
            max_claims=data.max_claims,
            model_name=data.model_name,
            provider_id=data.provider_id,
        )
        if not result["ok"]:
            return R.error(msg=result["message"], code=result["code"])
        return R.success(data=result["data"])
    except Exception as e:
        logger.error(f"联网核验失败 (task_id={data.task_id}): {e}", exc_info=True)
        return R.error(msg=f"联网核验失败: {e}")


@router.post("/verification_tasks")
def create_verification_task(data: VerificationTaskRequest, background_tasks: BackgroundTasks):
    try:
        created = NOTE_TASKS.create_verification_task(
            text=data.text or "",
            url=data.url or "",
            source_task_id=data.task_id,
            max_claims=data.max_claims,
            verification_depth=data.verification_depth,
            source_policy=data.source_policy,
            model_name=data.model_name,
            provider_id=data.provider_id,
        )
        background_tasks.add_task(NOTE_TASKS.execute_verification_task, created["task_id"])
        return R.success(created)
    except Exception as e:
        logger.error(f"创建联网核实任务失败: {e}", exc_info=True)
        return R.error(msg=f"创建联网核实任务失败: {e}")


@router.get("/verification_tasks")
def list_verification_tasks():
    return R.success(NOTE_TASKS.list_verification_tasks())


@router.get("/verification_tasks/{task_id}")
def get_verification_task(task_id: str):
    return R.success(NOTE_TASKS.get_verification_task(task_id))


@router.post("/verification_tasks/{task_id}/rerun")
def rerun_verification_task(task_id: str, data: VerificationRerunRequest | None = None):
    result = NOTE_TASKS.rerun_verification_task(
        task_id,
        retry_failed_only=True if data is None else data.retry_failed_only,
    )
    if not result["ok"]:
        return R.error(msg=result["message"], code=result["code"])
    return R.success(result["data"])


@router.post("/verification_tasks/{task_id}/claims/{claim_id}/rerun")
def rerun_verification_claim(task_id: str, claim_id: str):
    result = NOTE_TASKS.rerun_verification_claim(task_id, claim_id)
    if not result["ok"]:
        return R.error(msg=result["message"], code=result["code"])
    return R.success(result["data"])


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
def save_personal_summary(task_id: str, data: PersonalSummaryRequest):
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
        return R.success(NOTE_TASKS.get_task_status(created["task_id"]))
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
    if _safe_upload_extension(file.filename or "") != ".pdf":
        raise HTTPException(status_code=400, detail="论文导入当前仅支持 PDF")
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
    temp_pdf = stored_pdf.with_suffix(".pdf.part")
    try:
        with open(temp_pdf, "wb") as handle:
            handle.write(body)
        os.replace(temp_pdf, stored_pdf)
        persisted_source_url = source_url or f"{UPLOADS_PATH.rstrip('/')}/{safe_name}"
        created = PAPERS.ingest_pdf(
            content=bytes(body),
            filename=file.filename or "paper.pdf",
            source_url=persisted_source_url,
            provider_id=provider_id,
            model_name=model_name,
            overrides={"venue": venue, "doi": doi, "year": year},
        )
        return R.success(NOTE_TASKS.get_task_status(created["task_id"]))
    except ValueError as exc:
        if temp_pdf.exists():
            temp_pdf.unlink()
        if stored_pdf.exists():
            stored_pdf.unlink()
        return R.error(msg=str(exc), code=400)
    except Exception as exc:
        if temp_pdf.exists():
            temp_pdf.unlink()
        if stored_pdf.exists():
            stored_pdf.unlink()
        logger.error(f"导入 PDF 失败: {exc}", exc_info=True)
        return R.error(msg=f"导入 PDF 失败: {exc}")


@router.post("/upload")
async def upload(_: None = Depends(require_local_request), file: UploadFile = File(...)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = _safe_upload_extension(file.filename or "")
    safe_name = f"{uuid.uuid4().hex}{ext}"
    file_location = UPLOAD_DIR / safe_name
    temp_location = file_location.with_suffix(f"{file_location.suffix}.part")
    total = 0

    try:
        with open(temp_location, "wb") as f:
            while True:
                chunk = await file.read(IO_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="文件过大")
                f.write(chunk)
        os.replace(temp_location, file_location)
    except Exception:
        if temp_location.exists():
            temp_location.unlink()
        raise

    return R.success({"url": f"{UPLOADS_PATH.rstrip('/')}/{safe_name}"})


@router.post("/generate_note")
def generate_note(data: VideoRequest, background_tasks: BackgroundTasks):
    try:
        if data.task_id:
            task_id = data.task_id
            logger.info(f"重试模式，复用已有 task_id={task_id}")
        else:
            task_id = str(uuid.uuid4())

        NOTE_TASKS.prepare_generation_task(
            video_url=data.video_url,
            platform=data.platform,
            task_id=task_id,
            collection_folder=data.collection_folder or "默认收藏夹",
            collection_tags=data.collection_tags,
            collection_note=data.collection_note or "",
            prefetched_transcript=data.prefetched_transcript,
        )

        background_tasks.add_task(run_note_task, task_id, data.video_url, data.platform, data.quality, data.link,
                                  data.screenshot, data.model_name, data.provider_id, data.format, data.style,
                                  data.extras, data.video_understanding, data.video_interval, data.grid_size)
        return R.success({"task_id": task_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks")
def list_generated_tasks():
    return R.success(NOTE_TASKS.list_tasks())


@router.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    return R.success(NOTE_TASKS.get_task_status(task_id))


@router.get("/image_proxy")
async def image_proxy(request: Request, url: str):
    safe_url = _assert_public_image_url(url)
    headers = {
        "Referer": "https://www.douyin.com/",
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("GET", safe_url, headers=headers, follow_redirects=False) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail="图片获取失败")

                content_type = resp.headers.get("Content-Type", "image/jpeg")
                if not content_type.lower().startswith("image/"):
                    raise HTTPException(status_code=415, detail="代理目标不是图片")

                _assert_content_length_within_limit(resp.headers, MAX_IMAGE_PROXY_BYTES)
                body = bytearray()
                async for chunk in resp.aiter_bytes(IO_CHUNK_SIZE):
                    body.extend(chunk)
                    if len(body) > MAX_IMAGE_PROXY_BYTES:
                        raise HTTPException(status_code=413, detail="图片过大")

            return Response(
                content=bytes(body),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  #  缓存一天
                    "Content-Type": content_type,
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
