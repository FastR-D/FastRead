import logging
from dataclasses import asdict
from typing import Optional

from app.downloaders.base import Downloader
from app.enmus.task_status_enums import TaskStatus
from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.repositories.note_artifacts import NoteArtifactRepository
from app.transcriber.base import Transcriber
from app.transcriber.transcriber_provider import _transcribers, get_transcriber

logger = logging.getLogger(__name__)


class TranscriptService:
    """Handles transcript cache, subtitle lookup, ASR fallback, and metadata enrichment."""

    def __init__(
        self,
        artifacts: NoteArtifactRepository,
        transcriber_type: str,
        model_size: str,
        device: Optional[str] = None,
        transcriber: Optional[Transcriber] = None,
    ):
        self.artifacts = artifacts
        self.transcriber_type = transcriber_type
        self.model_size = model_size
        self.device = device
        self.transcriber = transcriber or self._init_transcriber()

    def get_prefetched_or_subtitle_transcript(
        self,
        task_id: str,
        downloader: Downloader,
        video_url: str,
    ) -> Optional[TranscriptResult]:
        transcript = self._load_real_transcript_cache(task_id, reload_metadata_only=False)
        if transcript:
            logger.info(f"已从缓存加载转写结果，共 {len(transcript.segments)} 段")
            return transcript

        logger.info("尝试获取平台字幕（优先于音频下载）...")
        try:
            transcript = downloader.download_subtitles(video_url)
            if transcript and transcript.segments:
                logger.info(f"成功获取平台字幕，共 {len(transcript.segments)} 段")
                self.artifacts.write_transcript_cache(task_id, asdict(transcript))
                return transcript
            logger.info("平台无可用字幕，将下载音频后转写")
        except Exception as exc:
            logger.warning(f"获取平台字幕失败: {exc}，将下载音频后转写")
        return None

    def get_or_create_transcript(
        self,
        task_id: str,
        downloader: Downloader,
        video_url: str,
        audio_file: str,
        update_status,
    ) -> TranscriptResult:
        update_status(task_id, TaskStatus.TRANSCRIBING)
        transcript = self._load_real_transcript_cache(task_id, reload_metadata_only=True)
        if transcript:
            return transcript

        logger.info("尝试获取平台字幕...")
        try:
            transcript = downloader.download_subtitles(video_url)
            if transcript and transcript.segments:
                logger.info(f"成功获取平台字幕，共 {len(transcript.segments)} 段")
                self.artifacts.write_transcript_cache(task_id, asdict(transcript))
                return transcript
            logger.info("平台无可用字幕，将使用音频转写")
        except Exception as exc:
            logger.warning(f"获取平台字幕失败: {exc}，将使用音频转写")

        return self.transcribe_audio(
            task_id=task_id,
            audio_file=audio_file,
            update_status=update_status,
        )

    def transcribe_audio(
        self,
        task_id: str,
        audio_file: str,
        update_status,
    ) -> TranscriptResult:
        update_status(task_id, TaskStatus.TRANSCRIBING)
        transcript_cache_file = self.artifacts.transcript_cache_path(task_id)

        transcript = self._load_real_transcript_cache(task_id, reload_metadata_only=True)
        if transcript:
            return transcript

        try:
            logger.info("开始转写音频")
            transcript = self.transcriber.transcript(file_path=audio_file)
            if not self.is_transcript_usable(transcript):
                raise RuntimeError("转写器未返回可用文本")
            self.artifacts.write_transcript_cache(task_id, asdict(transcript))
            logger.info(f"转写并缓存成功 ({transcript_cache_file})")
            return transcript
        except Exception as exc:
            if self.transcriber_type != "fast-whisper":
                try:
                    logger.warning(f"音频转写失败，准备使用 fast-whisper 兜底：{exc}")
                    fallback_transcriber = self._get_fallback_transcriber()
                    transcript = fallback_transcriber.transcript(file_path=audio_file)
                    if not self.is_transcript_usable(transcript):
                        raise RuntimeError("fast-whisper 未返回可用文本")
                    self.artifacts.write_transcript_cache(task_id, asdict(transcript))
                    logger.info(f"fast-whisper 转写并缓存成功 ({transcript_cache_file})")
                    return transcript
                except Exception as fallback_exc:
                    logger.error(f"fast-whisper 兜底转写失败：{fallback_exc}")
                    raise

            logger.error(f"音频转写失败：{exc}")
            raise

    def enrich_with_metadata(
        self,
        transcript: TranscriptResult,
        audio_meta: AudioDownloadResult,
    ) -> TranscriptResult:
        metadata_text = self._metadata_text(audio_meta)
        if not metadata_text:
            return transcript

        if not self.is_transcript_usable(transcript):
            return TranscriptResult(
                language="zh",
                full_text=metadata_text,
                segments=[TranscriptSegment(start=0, end=0, text=metadata_text)],
                raw={"source": "douyin_metadata"},
            )

        raw = dict(transcript.raw or {})
        if raw.get("source") == "douyin_metadata":
            existing_text = transcript.full_text or ""
            if metadata_text and metadata_text not in existing_text:
                merged_text = f"{existing_text}\n\n{metadata_text}".strip()
                return TranscriptResult(
                    language=transcript.language or "zh",
                    full_text=merged_text,
                    segments=[
                        *transcript.segments,
                        TranscriptSegment(start=0, end=0, text=metadata_text),
                    ],
                    raw=raw,
                )
            return transcript

        if not self._is_low_confidence_transcript(transcript):
            return transcript

        merged_text = f"{metadata_text}\n\n音频转写参考：{transcript.full_text}".strip()
        merged_segments = [
            TranscriptSegment(start=0, end=0, text=metadata_text),
            *transcript.segments,
        ]
        raw["metadata_enriched"] = True
        return TranscriptResult(
            language="zh",
            full_text=merged_text,
            segments=merged_segments,
            raw=raw,
        )

    def _init_transcriber(self) -> Transcriber:
        if self.transcriber_type not in _transcribers:
            logger.error(f"未找到支持的转写器：{self.transcriber_type}")
            raise Exception(f"不支持的转写器：{self.transcriber_type}")

        logger.info(f"使用转写器：{self.transcriber_type}")
        return get_transcriber(transcriber_type=self.transcriber_type)

    def _get_fallback_transcriber(self) -> Transcriber:
        logger.warning(
            f"当前转写器 {self.transcriber_type} 失败，尝试回退到 fast-whisper ({self.model_size})"
        )
        return get_transcriber(
            transcriber_type="fast-whisper",
            model_size=self.model_size,
            device=self.device or "cpu",
        )

    def _load_real_transcript_cache(
        self,
        task_id: str,
        reload_metadata_only: bool,
    ) -> Optional[TranscriptResult]:
        transcript_cache_file = self.artifacts.transcript_cache_path(task_id)
        data = self.artifacts.read_transcript_cache(task_id)
        if not data:
            return None

        logger.info(f"检测到转写缓存 ({transcript_cache_file})，尝试读取")
        try:
            segments = [TranscriptSegment(**seg) for seg in data.get("segments", [])]
            transcript = TranscriptResult(
                language=data.get("language"),
                full_text=data["full_text"],
                segments=segments,
                raw=data.get("raw"),
            )
            if self.is_real_transcript(transcript):
                return transcript
            if self.is_metadata_only_transcript(transcript):
                logger.info("转写缓存仅包含抖音元信息，将重新获取" if reload_metadata_only else "转写缓存仅包含抖音元信息，将重新下载音频转写")
            else:
                logger.info("转写缓存为空，将重新获取" if reload_metadata_only else "转写缓存为空，将重新下载音频转写")
        except Exception as exc:
            logger.warning(f"加载转写缓存失败: {exc}")
        return None

    @staticmethod
    def is_transcript_usable(transcript: Optional[TranscriptResult]) -> bool:
        if not transcript:
            return False
        if transcript.full_text and transcript.full_text.strip():
            return True
        return bool(transcript.segments)

    @staticmethod
    def is_metadata_only_transcript(transcript: Optional[TranscriptResult]) -> bool:
        if not transcript:
            return False
        raw = transcript.raw or {}
        return raw.get("source") == "douyin_metadata"

    @classmethod
    def is_real_transcript(cls, transcript: Optional[TranscriptResult]) -> bool:
        return cls.is_transcript_usable(transcript) and not cls.is_metadata_only_transcript(transcript)

    @staticmethod
    def _metadata_text(audio_meta: AudioDownloadResult) -> str:
        raw_info = audio_meta.raw_info or {}
        parts = []
        title = audio_meta.title or raw_info.get("title")
        caption = raw_info.get("caption") or raw_info.get("metadata_text") or ""
        desc = raw_info.get("desc")
        hashtags = raw_info.get("hashtags") or raw_info.get("tags")

        if title:
            parts.append(f"标题：{title}")
        if caption:
            parts.append(f"视频文案：{caption}")
        if desc and (not caption or desc not in caption):
            parts.append(f"描述：{desc}")
        if hashtags:
            if isinstance(hashtags, list):
                parts.append("标签：" + "、".join(str(tag) for tag in hashtags if tag))
            else:
                parts.append(f"标签：{hashtags}")

        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _is_low_confidence_transcript(transcript: TranscriptResult) -> bool:
        text = (transcript.full_text or "").strip()
        if len(text) < 80:
            return True

        ascii_chars = sum(1 for char in text if char.isascii() and char.isalpha())
        chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        if ascii_chars > chinese_chars * 2 and chinese_chars < 30:
            return True

        raw = transcript.raw or {}
        language = raw.get("language") or transcript.language
        language_probability = raw.get("language_probability")
        if language and language not in {"zh", "zh-cn", "zh-tw", "yue"}:
            if language_probability is None or float(language_probability) < 0.7:
                return True

        return False
