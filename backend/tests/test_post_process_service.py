from pathlib import Path

from app.models.audio_model import AudioDownloadResult
from app.services.post_process_service import PostProcessService


def audio_meta(video_id="123"):
    return AudioDownloadResult(
        file_path="audio.mp3",
        title="视频标题",
        duration=12,
        cover_url="",
        platform="douyin",
        video_id=video_id,
        raw_info={},
    )


def test_process_adds_source_and_replaces_content_marker():
    service = PostProcessService()

    markdown = service.process(
        markdown="段落 Content-01:02",
        video_url="https://example.com/source",
        formats=["link"],
        audio_meta=audio_meta("987"),
        platform="douyin",
    )

    assert markdown.startswith("> 来源链接：https://example.com/source")
    assert "[原片 @ 01:02](https://www.douyin.com/video/987)" in markdown


def test_insert_screenshots_replaces_markers(monkeypatch, tmp_path):
    image_file = tmp_path / "shot.jpg"
    image_file.write_bytes(b"image")
    service = PostProcessService(image_output_dir=str(tmp_path), image_base_url="/static/screenshots")

    monkeypatch.setattr(
        "app.services.post_process_service.generate_screenshot",
        lambda video_path, output_dir, timestamp, index: str(image_file),
    )

    markdown = service.insert_screenshots("看这里 Screenshot-00:03", Path("video.mp4"))

    assert markdown == "看这里 ![](/static/screenshots/shot.jpg)"


def test_screenshot_failure_keeps_original_markdown(monkeypatch):
    service = PostProcessService()

    def fail(*args, **kwargs):
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr("app.services.post_process_service.generate_screenshot", fail)

    markdown = service.apply_format_markers(
        markdown="看这里 Screenshot-00:03",
        video_path=Path("video.mp4"),
        formats=["screenshot"],
        audio_meta=audio_meta(),
        platform="douyin",
    )

    assert markdown == "看这里 Screenshot-00:03"
