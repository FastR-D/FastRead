from dataclasses import dataclass
from typing import List, Optional

from app.enmus.task_status_enums import TaskStatus
from app.gpt.base import GPT
from app.models.audio_model import AudioDownloadResult
from app.models.gpt_model import GPTSource
from app.models.transcriber_model import TranscriptResult
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.insight_extractor import build_insights
from app.services.transcript_service import TranscriptService
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SummaryResult:
    markdown: str
    insights: dict


class SummaryService:
    """Handles GPT summarization, markdown cache, and derived insights."""

    def __init__(self, artifacts: NoteArtifactRepository):
        self.artifacts = artifacts

    def generate(
        self,
        task_id: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        gpt: GPT,
        link: bool,
        screenshot: bool,
        formats: List[str],
        style: Optional[str],
        extras: Optional[str],
        video_img_urls: List[str],
        update_status,
    ) -> SummaryResult:
        markdown = self.summarize_text(
            task_id=task_id,
            audio_meta=audio_meta,
            transcript=transcript,
            gpt=gpt,
            link=link,
            screenshot=screenshot,
            formats=formats,
            style=style,
            extras=extras,
            video_img_urls=video_img_urls,
            update_status=update_status,
        )
        return SummaryResult(markdown=markdown, insights={})

    def build_insights(
        self,
        markdown: str,
        transcript: TranscriptResult,
        audio_meta: AudioDownloadResult,
        gpt: GPT,
    ) -> dict:
        return build_insights(markdown, transcript, audio_meta, gpt=gpt)

    def summarize_text(
        self,
        task_id: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        gpt: GPT,
        link: bool,
        screenshot: bool,
        formats: List[str],
        style: Optional[str],
        extras: Optional[str],
        video_img_urls: List[str],
        update_status,
    ) -> str:
        update_status(task_id, TaskStatus.SUMMARIZING)

        if not TranscriptService.is_transcript_usable(transcript):
            raise ValueError("转写结果为空，无法生成笔记")

        source = GPTSource(
            title=audio_meta.title,
            segment=transcript.segments,
            tags=audio_meta.raw_info.get("tags", []),
            screenshot=screenshot,
            video_img_urls=video_img_urls,
            link=link,
            _format=formats,
            style=style,
            extras=extras,
            checkpoint_key=task_id,
        )

        markdown = gpt.summarize(source)
        markdown_cache_file = self.artifacts.write_markdown_cache(task_id, markdown)
        logger.info(f"GPT 总结并缓存成功 ({markdown_cache_file})")
        return markdown
