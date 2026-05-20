import logging
import os
from dataclasses import asdict
from typing import List, Optional, Union

from pydantic import HttpUrl
from dotenv import load_dotenv

from app.downloaders.base import Downloader
from app.enmus.exception import NoteErrorEnum
from app.enmus.task_status_enums import TaskStatus
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.gpt.base import GPT
from app.models.notes_model import NoteResult
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.constant import SUPPORT_PLATFORM_MAP
from app.services.gpt_provider import GPTProvider
from app.services.note_lifecycle_service import NoteLifecycleService
from app.services.media_service import MediaService
from app.services.post_process_service import PostProcessService
from app.services.summary_service import SummaryService
from app.services.transcript_service import TranscriptService

# ------------------ 环境变量与全局配置 ------------------

# 从 .env 文件中加载环境变量
load_dotenv()

# 后端 API 地址与端口（若有需要可以在代码其他部分使用 BACKEND_BASE_URL）
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8483")
BACKEND_BASE_URL = f"{API_BASE_URL}:{BACKEND_PORT}"

# 输出目录（用于缓存音频、转写、Markdown 文件，以及存储截图）
ARTIFACTS = NoteArtifactRepository(os.getenv("NOTE_OUTPUT_DIR", "note_results"))
ARTIFACTS.ensure_output_dir()

# 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class NoteGenerator:
    """
    NoteGenerator 用于执行视频/音频下载、转写、GPT 生成笔记、插入截图/链接、
    以及将任务信息写入状态文件与数据库等功能。
    """

    def __init__(self):
        from app.services.transcriber_config_manager import TranscriberConfigManager
        config_manager = TranscriberConfigManager()
        self.model_size: str = config_manager.get_whisper_model_size()
        self.device: Optional[str] = None
        self.transcriber_type: str = config_manager.get_transcriber_type()
        self.artifacts = ARTIFACTS
        self.lifecycle = NoteLifecycleService(artifacts=self.artifacts)
        self.media_service = MediaService(artifacts=self.artifacts)
        self.post_process_service = PostProcessService()
        self.summary_service = SummaryService(artifacts=self.artifacts)
        self.transcript_service = TranscriptService(
            artifacts=self.artifacts,
            transcriber_type=self.transcriber_type,
            model_size=self.model_size,
            device=self.device,
        )
        logger.info("NoteGenerator 初始化完成")


    # ---------------- 公有方法 ----------------

    def generate(
        self,
        video_url: Union[str, HttpUrl],
        platform: str,
        quality: DownloadQuality = DownloadQuality.medium,
        task_id: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        link: bool = False,
        screenshot: bool = False,
        _format: Optional[List[str]] = None,
        style: Optional[str] = None,
        extras: Optional[str] = None,
        output_path: Optional[str] = None,
        video_understanding: bool = False,
        video_interval: int = 0,
        grid_size: Optional[List[int]] = None,
    ) -> NoteResult | None:
        """
        主流程：按步骤依次下载、转写、GPT 总结、截图/链接处理、存库、返回 NoteResult。

        :param video_url: 视频或音频链接
        :param platform: 平台名称，对应 SUPPORT_PLATFORM_MAP 中的键
        :param quality: 下载音频的质量枚举
        :param task_id: 用于标识本次任务的唯一 ID，亦用于状态文件和缓存文件命名
        :param model_name: GPT 模型名称
        :param provider_id: 模型供应商 ID
        :param link: 是否在笔记中插入视频片段链接
        :param screenshot: 是否在笔记中替换 Screenshot 标记为图片
        :param _format: 包含 'link' 或 'screenshot' 等字符串的列表，决定后续处理
        :param style: GPT 生成笔记的风格
        :param extras: 额外参数，传递给 GPT
        :param output_path: 下载输出目录（可选）
        :param video_understanding: 是否需要视频拼图理解（生成缩略图）
        :param video_interval: 视频帧截取间隔（秒），仅在 video_understanding 为 True 时生效
        :param grid_size: 生成缩略图时的网格大小，如 [3, 3]
        :return: NoteResult 对象，包含 markdown 文本、转写结果和音频元信息
        """
        if grid_size is None:
            grid_size = []

        try:
            logger.info(f"开始生成笔记 (task_id={task_id})")
            self.lifecycle.update_status(task_id, TaskStatus.PARSING)

            # 获取下载器与 GPT 实例

            downloader = self._get_downloader(platform)
            gpt = self._get_gpt(model_name, provider_id)

            # 1. 获取字幕/转写：优先缓存 → 平台字幕 → 音频转写
            transcript = self.transcript_service.get_prefetched_or_subtitle_transcript(
                task_id=task_id,
                downloader=downloader,
                video_url=str(video_url),
            )

            # 2. 下载音频/视频
            # 有字幕时只提取元信息，不下载音视频文件（除非需要截图/视频理解）
            has_transcript = transcript is not None
            need_full_download = not has_transcript or screenshot or video_understanding
            media_result = self.media_service.download_media(
                downloader=downloader,
                video_url=video_url,
                quality=quality,
                task_id=task_id,
                status_phase=TaskStatus.DOWNLOADING,
                output_path=output_path,
                screenshot=screenshot,
                video_understanding=video_understanding,
                video_interval=video_interval,
                grid_size=grid_size,
                update_status=self.lifecycle.update_status,
                handle_exception=self.lifecycle.handle_exception,
                skip_download=not need_full_download,
            )
            audio_meta = media_result.audio_meta

            # 3. 如果前面没拿到字幕，走转写流程
            if transcript is None:
                transcript = self.transcript_service.get_or_create_transcript(
                    task_id=task_id,
                    downloader=downloader,
                    video_url=video_url,
                    audio_file=audio_meta.file_path,
                    update_status=self.lifecycle.update_status,
                )
            transcript = self.transcript_service.enrich_with_metadata(transcript, audio_meta)
            self.artifacts.write_transcript_cache(task_id, asdict(transcript))

            # 3. GPT 总结与洞察
            summary_result = self.summary_service.generate(
                task_id=task_id,
                audio_meta=audio_meta,
                transcript=transcript,
                gpt=gpt,
                link=link,
                screenshot=screenshot,
                formats=_format or [],
                style=style,
                extras=extras,
                video_img_urls=media_result.video_img_urls,
                update_status=self.lifecycle.update_status,
            )
            markdown = summary_result.markdown

            # 4. 截图、链接替换、来源链接
            markdown = self.post_process_service.process(
                markdown=markdown,
                video_url=str(video_url),
                formats=_format or [],
                audio_meta=audio_meta,
                platform=platform,
                video_path=media_result.video_path,
            )
            insights = self.summary_service.build_insights(markdown, transcript, audio_meta, gpt=gpt)

            # 5. 保存记录到数据库
            self.lifecycle.update_status(task_id, TaskStatus.SAVING)
            self.lifecycle.save_metadata(
                video_id=audio_meta.video_id,
                platform=platform,
                task_id=task_id,
                title=audio_meta.title,
                cover_url=audio_meta.cover_url,
            )

            # 6. 完成
            self.lifecycle.update_status(task_id, TaskStatus.SUCCESS)
            logger.info(f"笔记生成成功 (task_id={task_id})")
            return NoteResult(markdown=markdown, transcript=transcript, audio_meta=audio_meta, insights=insights)

        except Exception as exc:
            logger.error(f"生成笔记流程异常 (task_id={task_id})：{exc}", exc_info=True)
            self.lifecycle.update_status(task_id, TaskStatus.FAILED, message=str(exc))
            return None

    @staticmethod
    def delete_note(video_id: str, platform: str) -> int:
        """
        删除数据库中对应 video_id 与 platform 的任务记录

        :param video_id: 视频 ID
        :param platform: 平台标识
        :return: 删除的记录数
        """
        return NoteLifecycleService.delete_note(video_id, platform)

    # ---------------- 私有方法 ----------------

    def _get_gpt(self, model_name: Optional[str], provider_id: Optional[str]) -> GPT:
        """
        根据 provider_id 获取对应的 GPT 实例
        :param model_name: GPT 模型名称
        :param provider_id: 供应商 ID
        :return: GPT 实例
        """
        return GPTProvider.create(provider_id=provider_id, model_name=model_name)

    def _get_downloader(self, platform: str) -> Downloader:
        """
        根据平台名称获取对应的下载器实例

        :param platform: 平台标识，需在 SUPPORT_PLATFORM_MAP 中
        :return: 对应的 Downloader 子类实例
        """
        downloader_cls = SUPPORT_PLATFORM_MAP.get(platform)
        logger.debug(f"实例化下载器 -  {platform}")
        instance = None
        if not downloader_cls:
            logger.error(f"不支持的平台：{platform}")
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)
        try:
            instance = downloader_cls
        except Exception as e:
            logger.error(f"实例化下载器失败：{e}")


        logger.info(f"使用下载器：{downloader_cls.__class__}")
        return instance
