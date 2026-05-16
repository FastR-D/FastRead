import os
import re
from pathlib import Path
from typing import Optional, Union

from yt_dlp import YoutubeDL

from app.downloaders.base import Downloader
from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult
from app.services.cookie_manager import CookieConfigManager
from app.utils.path_helper import get_data_dir

cfm = CookieConfigManager()


class YtDlpDownloader(Downloader):
    def __init__(self, platform: str):
        super().__init__()
        self.platform = platform

    def _base_opts(self, output_dir: str, skip_download: bool = False) -> dict:
        opts = {
            "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": skip_download,
        }
        cookie = cfm.get(self.platform)
        if cookie:
            opts["http_headers"] = {"Cookie": cookie}
        return opts

    def _output_dir(self, output_dir: Optional[str]) -> str:
        target = output_dir or get_data_dir() or self.cache_data or "data"
        os.makedirs(target, exist_ok=True)
        return target

    @staticmethod
    def _metadata_text(info: dict) -> str:
        tags = info.get("tags") or []
        categories = info.get("categories") or []
        parts = [
            info.get("title") or "",
            info.get("description") or "",
            "、".join(str(tag) for tag in [*tags, *categories] if tag),
        ]
        return "\n".join(part.strip() for part in parts if str(part).strip())

    @staticmethod
    def _find_downloaded_file(output_dir: str, video_id: str, suffixes: tuple[str, ...]) -> str:
        for suffix in suffixes:
            path = Path(output_dir) / f"{video_id}.{suffix}"
            if path.exists():
                return str(path)
        matches = sorted(Path(output_dir).glob(f"{video_id}.*"))
        return str(matches[0]) if matches else str(Path(output_dir) / f"{video_id}.{suffixes[0]}")

    def extract_info(self, video_url: str, output_dir: Optional[str] = None, download: bool = False,
                     opts: Optional[dict] = None) -> dict:
        target_dir = self._output_dir(output_dir)
        ydl_opts = self._base_opts(target_dir, skip_download=not download)
        if opts:
            ydl_opts.update(opts)
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video_url, download=download)

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video: Optional[bool] = False,
        skip_download: bool = False,
    ) -> AudioDownloadResult:
        target_dir = self._output_dir(output_dir)
        opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
        }
        info = self.extract_info(video_url, target_dir, download=not skip_download, opts=opts)
        video_id = str(info.get("id") or self._fallback_video_id(video_url))
        audio_path = self._find_downloaded_file(target_dir, video_id, ("mp3", "m4a", "webm", "mp4"))

        return AudioDownloadResult(
            file_path=audio_path,
            title=(info.get("title") or video_id)[:120],
            duration=float(info.get("duration") or 0),
            cover_url=info.get("thumbnail"),
            platform=self.platform,
            video_id=video_id,
            raw_info={
                "title": info.get("title"),
                "desc": info.get("description") or "",
                "caption": info.get("description") or "",
                "metadata_text": self._metadata_text(info),
                "uploader": info.get("uploader") or info.get("channel") or "",
                "webpage_url": info.get("webpage_url") or video_url,
                "tags": info.get("tags") or info.get("categories") or [],
            },
            video_path=None,
        )

    def download_video(self, video_url: str, output_dir: Union[str, None] = None) -> str:
        target_dir = self._output_dir(output_dir)
        info = self.extract_info(
            video_url,
            target_dir,
            download=True,
            opts={"format": "bestvideo+bestaudio/best", "merge_output_format": "mp4"},
        )
        video_id = str(info.get("id") or self._fallback_video_id(video_url))
        return self._find_downloaded_file(target_dir, video_id, ("mp4", "mkv", "webm"))

    def download_subtitles(self, video_url: str, output_dir: str = None,
                           langs: list = None) -> Optional[TranscriptResult]:
        return None

    @staticmethod
    def _fallback_video_id(video_url: str) -> str:
        match = re.search(r"(BV[0-9A-Za-z]+|av\d+|video/(\d+)|short-video/(\w+)|photo/(\w+))", video_url)
        if match:
            return next(group for group in match.groups() if group)
        return re.sub(r"\W+", "_", video_url).strip("_")[:80] or "video"
