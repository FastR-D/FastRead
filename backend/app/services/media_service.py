from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Union

from pydantic import HttpUrl

from app.downloaders.base import Downloader
from app.enmus.note_enums import DownloadQuality
from app.enmus.task_status_enums import TaskStatus
from app.models.audio_model import AudioDownloadResult
from app.repositories.note_artifacts import NoteArtifactRepository
from app.utils.logger import get_logger
from app.utils.video_reader import VideoReader

logger = get_logger(__name__)


@dataclass
class MediaDownloadResult:
    audio_meta: AudioDownloadResult
    video_path: Optional[Path] = None
    video_img_urls: List[str] = field(default_factory=list)


class MediaService:
    """Handles media metadata/audio/video download and video-understanding grids."""

    def __init__(self, artifacts: NoteArtifactRepository):
        self.artifacts = artifacts

    def download_media(
        self,
        downloader: Downloader,
        video_url: Union[str, HttpUrl],
        quality: DownloadQuality,
        task_id: str,
        status_phase: TaskStatus,
        output_path: Optional[str],
        screenshot: bool,
        video_understanding: bool,
        video_interval: int,
        grid_size: List[int],
        update_status: Callable,
        handle_exception: Callable,
        skip_download: bool = False,
    ) -> MediaDownloadResult:
        update_status(task_id, status_phase)
        audio_cache_file = self.artifacts.audio_cache_path(task_id)

        audio_cache = self.artifacts.read_audio_cache(task_id)
        if audio_cache:
            logger.info(f"检测到音频缓存 ({audio_cache_file})，直接读取")
            try:
                return MediaDownloadResult(audio_meta=AudioDownloadResult(**audio_cache))
            except Exception as exc:
                logger.warning(f"读取音频缓存失败，将重新下载：{exc}")

        if skip_download:
            logger.info("已有字幕，仅提取视频元信息（不下载音视频）")
            try:
                audio = downloader.download(
                    video_url=video_url,
                    quality=quality,
                    output_dir=output_path,
                    need_video=False,
                    skip_download=True,
                )
                self.artifacts.write_audio_cache(task_id, asdict(audio))
                logger.info(f"元信息提取完成 ({audio_cache_file})")
                return MediaDownloadResult(audio_meta=audio)
            except Exception as exc:
                logger.warning(f"元信息提取失败，将尝试完整下载: {exc}")

        need_video = screenshot or video_understanding
        if screenshot and not grid_size:
            grid_size = [2, 2]

        video_path = None
        video_img_urls: list[str] = []
        frame_interval = video_interval if video_interval and video_interval > 0 else 6
        if need_video:
            try:
                logger.info("开始下载视频")
                video_path = Path(downloader.download_video(video_url))
                logger.info(f"视频下载完成：{video_path}")

                if grid_size:
                    video_img_urls = VideoReader(
                        video_path=str(video_path),
                        grid_size=tuple(grid_size),
                        frame_interval=frame_interval,
                        unit_width=960,
                        unit_height=540,
                        save_quality=80,
                    ).run()
                else:
                    logger.info("未指定 grid_size，跳过缩略图生成")
            except Exception as exc:
                logger.error(f"视频下载失败：{exc}")
                handle_exception(task_id, exc)
                raise

        try:
            logger.info("开始下载音频")
            audio = downloader.download(
                video_url=video_url,
                quality=quality,
                output_dir=output_path,
                need_video=need_video,
            )
            self.artifacts.write_audio_cache(task_id, asdict(audio))
            logger.info(f"音频下载并缓存成功 ({audio_cache_file})")
            return MediaDownloadResult(
                audio_meta=audio,
                video_path=video_path,
                video_img_urls=video_img_urls,
            )
        except Exception as exc:
            logger.error(f"音频下载失败：{exc}")
            handle_exception(task_id, exc)
            raise
