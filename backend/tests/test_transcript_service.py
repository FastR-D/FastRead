from dataclasses import dataclass

import pytest

from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.transcript_service import TranscriptService


class DummyDownloader:
    def __init__(self, transcript=None, error=None):
        self.transcript = transcript
        self.error = error

    def download_subtitles(self, video_url):
        if self.error:
            raise self.error
        return self.transcript


class DummyTranscriber:
    def __init__(self, transcript):
        self.transcript_result = transcript
        self.calls = 0

    def transcript(self, file_path):
        self.calls += 1
        return self.transcript_result


def make_service(tmp_path, transcriber=None):
    return TranscriptService(
        artifacts=NoteArtifactRepository(tmp_path),
        transcriber_type="dummy",
        model_size="tiny",
        transcriber=transcriber or DummyTranscriber(
            TranscriptResult(
                language="zh",
                full_text="转写内容足够长，能够作为真实转写文本使用。" * 4,
                segments=[TranscriptSegment(start=0, end=1, text="转写内容")],
            )
        ),
    )


def test_prefetched_cache_wins_over_downloader(tmp_path):
    service = make_service(tmp_path)
    service.artifacts.write_transcript_cache("task-a", {
        "language": "zh",
        "full_text": "缓存字幕内容足够长，应该直接命中。" * 4,
        "segments": [{"start": 0, "end": 1, "text": "缓存字幕"}],
    })

    transcript = service.get_prefetched_or_subtitle_transcript(
        task_id="task-a",
        downloader=DummyDownloader(error=RuntimeError("should not call downloader")),
        video_url="https://example.com/video",
    )

    assert transcript.full_text.startswith("缓存字幕内容")


def test_transcribe_audio_uses_fallback_when_primary_fails(tmp_path, monkeypatch):
    class FailingTranscriber:
        def transcript(self, file_path):
            raise RuntimeError("primary failed")

    fallback = DummyTranscriber(
        TranscriptResult(
            language="zh",
            full_text="fallback 转写内容足够长，能够作为真实转写文本使用。" * 4,
            segments=[TranscriptSegment(start=0, end=1, text="fallback")],
        )
    )
    service = make_service(tmp_path, transcriber=FailingTranscriber())
    service.transcriber_type = "bcut"
    monkeypatch.setattr(service, "_get_fallback_transcriber", lambda: fallback)

    seen_statuses = []
    transcript = service.transcribe_audio(
        task_id="task-a",
        audio_file="audio.mp3",
        update_status=lambda task_id, status: seen_statuses.append(status.value),
    )

    assert transcript.full_text.startswith("fallback")
    assert fallback.calls == 1
    assert seen_statuses == ["TRANSCRIBING"]


def test_enrich_low_confidence_transcript_with_metadata(tmp_path):
    service = make_service(tmp_path)
    transcript = TranscriptResult(
        language="en",
        full_text="short",
        segments=[TranscriptSegment(start=0, end=1, text="short")],
        raw={"language_probability": 0.2},
    )
    audio_meta = AudioDownloadResult(
        video_id="v1",
        title="视频标题",
        duration=12,
        file_path="audio.mp3",
        cover_url="",
        platform="douyin",
        raw_info={"caption": "视频文案", "tags": ["知识"]},
    )

    enriched = service.enrich_with_metadata(transcript, audio_meta)

    assert enriched.raw["metadata_enriched"] is True
    assert "视频标题" in enriched.full_text
    assert "音频转写参考：short" in enriched.full_text
