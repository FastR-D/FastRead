import pytest

from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.summary_service import SummaryService


class DummyGPT:
    def __init__(self, markdown="# Summary"):
        self.markdown = markdown
        self.last_source = None

    def summarize(self, source):
        self.last_source = source
        return self.markdown


def audio_meta():
    return AudioDownloadResult(
        file_path="audio.mp3",
        title="视频标题",
        duration=12,
        cover_url="",
        platform="douyin",
        video_id="v1",
        raw_info={"tags": ["知识"]},
    )


def transcript(text="这是一段足够生成笔记的转写文本"):
    return TranscriptResult(
        language="zh",
        full_text=text,
        segments=[TranscriptSegment(start=0, end=1, text=text)],
    )


def test_summarize_text_builds_source_and_writes_cache(tmp_path):
    service = SummaryService(NoteArtifactRepository(tmp_path))
    gpt = DummyGPT("# Generated")
    statuses = []

    markdown = service.summarize_text(
        task_id="task-a",
        audio_meta=audio_meta(),
        transcript=transcript(),
        gpt=gpt,
        link=True,
        screenshot=True,
        formats=["link", "screenshot"],
        style="minimal",
        extras="extra",
        video_img_urls=["data:image/jpeg;base64,abc"],
        update_status=lambda task_id, status: statuses.append(status.value),
    )

    assert markdown == "# Generated"
    assert statuses == ["SUMMARIZING"]
    assert gpt.last_source.title == "视频标题"
    assert gpt.last_source.tags == ["知识"]
    assert gpt.last_source.video_img_urls == ["data:image/jpeg;base64,abc"]
    assert service.artifacts.markdown_cache_path("task-a").read_text(encoding="utf-8") == "# Generated"


def test_summarize_text_rejects_empty_transcript(tmp_path):
    service = SummaryService(NoteArtifactRepository(tmp_path))

    with pytest.raises(ValueError, match="转写结果为空"):
        service.summarize_text(
            task_id="task-a",
            audio_meta=audio_meta(),
            transcript=TranscriptResult(language="zh", full_text="", segments=[]),
            gpt=DummyGPT(),
            link=False,
            screenshot=False,
            formats=[],
            style=None,
            extras=None,
            video_img_urls=[],
            update_status=lambda task_id, status: None,
        )
