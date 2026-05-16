# app/routers/note.py
import json
import os
import uuid
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, field_validator
from dataclasses import asdict

from app.enmus.exception import NoteErrorEnum
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.services.note import NoteGenerator, logger
from app.services.task_serial_executor import task_serial_executor
from app.utils.response import ResponseWrapper as R
from app.utils.url_parser import extract_video_id
from app.validators.video_url_validator import is_supported_video_url
from fastapi import Request
from fastapi.responses import StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus
from app.db.video_task_dao import (
    delete_task_by_task_id,
    delete_task_by_video,
    list_video_tasks,
    update_task_collection,
    upsert_video_task,
)

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
        if v != "douyin":
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message="当前仅支持抖音精选视频")
        return v

    @field_validator("video_url")
    def validate_supported_url(cls, v):
        url = str(v)
        if not is_supported_video_url(url):
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message="请输入抖音精选视频链接")
        return v


NOTE_OUTPUT_DIR = os.getenv("NOTE_OUTPUT_DIR", "note_results")
UPLOAD_DIR = "uploads"


def _read_task_status(task_id: str) -> str:
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    if not os.path.exists(status_path):
        return TaskStatus.SUCCESS.value
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f).get("status") or TaskStatus.SUCCESS.value
    except Exception:
        return TaskStatus.SUCCESS.value


def _extract_source_url(markdown: str) -> str:
    if not markdown:
        return ""
    first_line = markdown.splitlines()[0] if markdown.splitlines() else ""
    prefix = "> 来源链接："
    return first_line.replace(prefix, "").strip() if first_line.startswith(prefix) else ""


def _created_at_to_timestamp(value) -> float:
    if not value:
        return 0
    try:
        return value.timestamp()
    except Exception:
        return 0


def _parse_collection_tags(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(tag).strip() for tag in raw if str(tag).strip()]
    return [tag.strip() for tag in str(raw).replace("，", ",").split(",") if tag.strip()]


def _is_note_result_file(path: Path) -> bool:
    if path.suffix != ".json":
        return False
    name = path.name
    ignored_suffixes = (
        ".status.json",
        "_status.json",
        "_transcript.json",
        "_audio.json",
        "_markdown.status.json",
    )
    return not any(name.endswith(suffix) for suffix in ignored_suffixes)


def save_note_to_file(task_id: str, note):
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
        json.dump(asdict(note), f, ensure_ascii=False, indent=2)


def _delete_task_files(task_id: str) -> int:
    result_dir = Path(NOTE_OUTPUT_DIR)
    if not result_dir.exists():
        return 0
    deleted = 0
    for path in result_dir.glob(f"{task_id}*"):
        try:
            if path.is_file() and path.resolve().parent == result_dir.resolve():
                path.unlink()
                deleted += 1
        except Exception as e:
            logger.warning(f"删除任务文件失败 ({path}): {e}")
    return deleted


def _persist_prefetched_transcript(task_id: str, transcript: dict) -> None:
    """把客户端预取的字幕写到 NoteGenerator 期望的转写缓存文件里。

    NoteGenerator.generate 会优先读 <task_id>_transcript.json，命中即跳过 download_subtitles
    与音频转写流程。要求字段：language(可空)/full_text/segments[{start,end,text}]
    """
    segments = transcript.get("segments") or []
    cleaned_segments = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        cleaned_segments.append({
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": text,
        })
    if not cleaned_segments:
        raise ValueError("prefetched_transcript 没有可用的 segments")

    full_text = transcript.get("full_text") or " ".join(s["text"] for s in cleaned_segments)
    payload = {
        "language": transcript.get("language") or "zh",
        "full_text": full_text,
        "segments": cleaned_segments,
    }

    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    target = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_transcript.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"已写入客户端预取字幕缓存: {target} ({len(cleaned_segments)} 段)")


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[]
                  ):

    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    def _execute_note_task():
        return NoteGenerator().generate(
            video_url=video_url,
            platform=platform,
            quality=quality,
            task_id=task_id,
            model_name=model_name,
            provider_id=provider_id,
            link=link,
            _format=_format,
            style=style,
            extras=extras,
            screenshot=screenshot,
            video_understanding=video_understanding,
            video_interval=video_interval,
            grid_size=grid_size,
        )

    logger.info(f"任务进入执行队列 (task_id={task_id})")
    note = task_serial_executor.run(_execute_note_task)
    logger.info(f"Note generated: {task_id}")
    if not note or not note.markdown:
        logger.warning(f"任务 {task_id} 执行失败，跳过保存")
        return
    save_note_to_file(task_id, note)

    # 自动建立向量索引（用于 AI 问答），失败不影响笔记生成
    try:
        from app.services.vector_store import VectorStoreManager
        VectorStoreManager().index_task(task_id)
    except Exception as e:
        logger.warning(f"向量索引失败（不影响笔记）: {e}")


@router.post('/delete_task')
def delete_task(data: RecordRequest):
    try:
        if data.task_id:
            delete_task_by_task_id(data.task_id)
            _delete_task_files(data.task_id)
            try:
                from app.services.vector_store import VectorStoreManager
                VectorStoreManager().delete_index(data.task_id)
            except Exception as e:
                logger.warning(f"删除向量索引失败（不影响任务删除）: {e}")
        elif data.video_id:
            delete_task_by_video(data.video_id, data.platform)
        return R.success(msg='删除成功')
    except Exception as e:
        return R.error(msg=e)


@router.post("/update_task_collection")
def update_collection(data: CollectionUpdateRequest):
    try:
        updated = update_task_collection(
            task_id=data.task_id,
            collection_folder=data.collection_folder,
            collection_tags=_parse_collection_tags(data.collection_tags),
            collection_note=data.collection_note,
        )
        if not updated:
            return R.error(msg="任务不存在", code=404)
        return R.success(data={
            "task_id": data.task_id,
            "collection": {
                "folder": updated.get("collection_folder") or "默认收藏夹",
                "tags": _parse_collection_tags(updated.get("collection_tags")),
                "note": updated.get("collection_note") or "",
            },
        })
    except Exception as e:
        return R.error(msg=e)


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_location = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_location, "wb+") as f:
        f.write(await file.read())

    # 假设你静态目录挂载了 /uploads
    return R.success({"url": f"/uploads/{file.filename}"})


@router.post("/generate_note")
def generate_note(data: VideoRequest, background_tasks: BackgroundTasks):
    try:

        video_id = extract_video_id(data.video_url, data.platform)
        # if not video_id:
        #     raise HTTPException(status_code=400, detail="无法提取视频 ID")
        # existing = get_task_by_video(video_id, data.platform)
        # if existing:
        #     return R.error(
        #         msg='笔记已生成，请勿重复发起',
        #
        #     )
        if data.task_id:
            # 如果传了task_id，说明是重试！
            task_id = data.task_id
            logger.info(f"重试模式，复用已有 task_id={task_id}")
        else:
            # 正常新建任务
            task_id = str(uuid.uuid4())

        collection_tags = _parse_collection_tags(data.collection_tags)
        upsert_video_task(
            video_id=video_id or "",
            platform=data.platform,
            task_id=task_id,
            video_url=data.video_url,
            collection_folder=data.collection_folder or "默认收藏夹",
            collection_tags=collection_tags,
            collection_note=data.collection_note or "",
        )

        # 统一先写入 PENDING，表示已进入队列等待串行执行
        NoteGenerator()._update_status(task_id, TaskStatus.PENDING)

        # 客户端已经抓好字幕的话，写到转写缓存文件，NoteGenerator 的 cache-hit 逻辑会直接用上
        if data.prefetched_transcript:
            try:
                _persist_prefetched_transcript(task_id, data.prefetched_transcript)
            except Exception as e:
                logger.warning(f"写入预取字幕失败 (task_id={task_id}): {e}")

        background_tasks.add_task(run_note_task, task_id, data.video_url, data.platform, data.quality, data.link,
                                  data.screenshot, data.model_name, data.provider_id, data.format, data.style,
                                  data.extras, data.video_understanding, data.video_interval, data.grid_size)
        return R.success({"task_id": task_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks")
def list_generated_tasks():
    result_dir = Path(NOTE_OUTPUT_DIR)
    db_tasks = list_video_tasks()
    if not result_dir.exists() and not db_tasks:
        return R.success([])

    tasks = []
    seen_task_ids = set()
    for db_task in db_tasks:
        task_id = db_task["task_id"]
        seen_task_ids.add(task_id)
        result_path = result_dir / f"{task_id}.json"
        result = {}
        if result_path.exists():
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
            except Exception as e:
                logger.warning(f"读取任务结果失败 (task_id={task_id}): {e}")

        markdown = result.get("markdown") or ""
        audio_meta = result.get("audio_meta") or {}
        tasks.append({
            "id": task_id,
            "status": _read_task_status(task_id),
            "markdown": markdown,
            "audioMeta": audio_meta,
            "createdAt": _created_at_to_timestamp(db_task.get("created_at")),
            "videoUrl": db_task.get("video_url") or _extract_source_url(markdown),
            "collection": {
                "folder": db_task.get("collection_folder") or "默认收藏夹",
                "tags": _parse_collection_tags(db_task.get("collection_tags")),
                "note": db_task.get("collection_note") or "",
            },
            "title": db_task.get("title") or audio_meta.get("title") or "",
            "coverUrl": db_task.get("cover_url") or audio_meta.get("cover_url") or "",
        })

    if not result_dir.exists():
        tasks.sort(key=lambda item: item["createdAt"], reverse=True)
        return R.success(tasks)

    for result_path in result_dir.iterdir():
        if not _is_note_result_file(result_path):
            continue

        task_id = result_path.stem
        if task_id in seen_task_ids:
            continue
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                result = json.load(f)
        except Exception as e:
            logger.warning(f"读取任务结果失败 (task_id={task_id}): {e}")
            continue

        markdown = result.get("markdown") or ""
        audio_meta = result.get("audio_meta") or {}
        tasks.append({
            "id": task_id,
            "status": _read_task_status(task_id),
            "markdown": markdown,
            "audioMeta": audio_meta,
            "createdAt": result_path.stat().st_mtime,
            "videoUrl": _extract_source_url(markdown),
        })

    tasks.sort(key=lambda item: item["createdAt"], reverse=True)
    return R.success(tasks)


@router.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")

    # 优先读状态文件
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_content = json.load(f)

        status = status_content.get("status")
        message = status_content.get("message", "")

        if status == TaskStatus.SUCCESS.value:
            # 成功状态的话，继续读取最终笔记内容
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as rf:
                    result_content = json.load(rf)
                return R.success({
                    "status": status,
                    "result": result_content,
                    "message": message,
                    "task_id": task_id
                })
            else:
                # 理论上不会出现，保险处理
                return R.success({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    "task_id": task_id
                })

        if status == TaskStatus.FAILED.value:
            return R.error(message or "任务失败", code=500)

        # 处理中状态
        return R.success({
            "status": status,
            "message": message,
            "task_id": task_id
        })

    # 没有状态文件，但有结果
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result_content = json.load(f)
        return R.success({
            "status": TaskStatus.SUCCESS.value,
            "result": result_content,
            "task_id": task_id
        })

    # 什么都没有，默认PENDING
    return R.success({
        "status": TaskStatus.PENDING.value,
        "message": "任务排队中",
        "task_id": task_id
    })


@router.get("/image_proxy")
async def image_proxy(request: Request, url: str):
    headers = {
        "Referer": "https://www.douyin.com/",
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="图片获取失败")

            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  #  缓存一天
                    "Content-Type": content_type,
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
