from app.enmus.note_enums import DownloadQuality
from app.enmus.task_status_enums import TaskStatus
from app.models.audio_model import AudioDownloadResult
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.media_service import MediaService


def audio_result(title="title", file_path="audio.mp3"):
    return AudioDownloadResult(
        file_path=file_path,
        title=title,
        duration=12,
        cover_url="",
        platform="douyin",
        video_id="v1",
        raw_info={"title": title},
    )


class DummyDownloader:
    def __init__(self):
        self.download_calls = []
        self.video_calls = 0

    def download(self, **kwargs):
        self.download_calls.append(kwargs)
        return audio_result(title="downloaded")

    def download_video(self, video_url):
        self.video_calls += 1
        return "video.mp4"


def noop_handle_exception(task_id, exc):
    raise AssertionError(f"unexpected error handler call: {task_id}, {exc}")


def test_audio_cache_wins_over_downloader(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    repo.write_audio_cache("task-a", audio_result(title="cached").__dict__)
    downloader = DummyDownloader()

    result = MediaService(repo).download_media(
        downloader=downloader,
        video_url="https://example.com/video",
        quality=DownloadQuality.medium,
        task_id="task-a",
        status_phase=TaskStatus.DOWNLOADING,
        output_path=None,
        screenshot=False,
        video_understanding=False,
        video_interval=0,
        grid_size=[],
        update_status=lambda task_id, status: None,
        handle_exception=noop_handle_exception,
    )

    assert result.audio_meta.title == "cached"
    assert downloader.download_calls == []
    assert downloader.video_calls == 0


def test_skip_download_extracts_metadata_only(tmp_path):
    downloader = DummyDownloader()

    result = MediaService(NoteArtifactRepository(tmp_path)).download_media(
        downloader=downloader,
        video_url="https://example.com/video",
        quality=DownloadQuality.medium,
        task_id="task-a",
        status_phase=TaskStatus.DOWNLOADING,
        output_path="out",
        screenshot=False,
        video_understanding=False,
        video_interval=0,
        grid_size=[],
        update_status=lambda task_id, status: None,
        handle_exception=noop_handle_exception,
        skip_download=True,
    )

    assert result.audio_meta.title == "downloaded"
    assert downloader.download_calls[0]["skip_download"] is True
    assert downloader.download_calls[0]["need_video"] is False
    assert downloader.video_calls == 0


def test_video_download_generates_grid_urls(tmp_path, monkeypatch):
    class DummyVideoReader:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            return ["data:image/jpeg;base64,abc"]

    monkeypatch.setattr("app.services.media_service.VideoReader", DummyVideoReader)
    downloader = DummyDownloader()
    seen_statuses = []

    result = MediaService(NoteArtifactRepository(tmp_path)).download_media(
        downloader=downloader,
        video_url="https://example.com/video",
        quality=DownloadQuality.medium,
        task_id="task-a",
        status_phase=TaskStatus.DOWNLOADING,
        output_path=None,
        screenshot=True,
        video_understanding=False,
        video_interval=3,
        grid_size=[],
        update_status=lambda task_id, status: seen_statuses.append(status.value),
        handle_exception=noop_handle_exception,
    )

    assert result.video_path.name == "video.mp4"
    assert result.video_img_urls == ["data:image/jpeg;base64,abc"]
    assert downloader.download_calls[0]["need_video"] is True
    assert downloader.video_calls == 1
    assert seen_statuses == ["DOWNLOADING"]
