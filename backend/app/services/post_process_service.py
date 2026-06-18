import os
from pathlib import Path
from typing import List, Optional

from app.core.settings import get_settings
from app.models.audio_model import AudioDownloadResult
from app.utils.logger import get_logger
from app.utils.note_helper import prepend_source_link, replace_content_markers
from app.utils.screenshot_marker import extract_screenshot_timestamps
from app.utils.video_helper import generate_screenshot

logger = get_logger(__name__)


class PostProcessService:
    """Applies generated markdown post-processing such as screenshots and source links."""

    def __init__(
        self,
        image_output_dir: str | None = None,
        image_base_url: str | None = None,
    ):
        settings = get_settings()
        self.image_output_dir = image_output_dir or settings.screenshot_output_dir
        self.image_base_url = image_base_url or settings.image_base_url

    def process(
        self,
        markdown: str,
        video_url: str,
        formats: Optional[List[str]],
        audio_meta: AudioDownloadResult,
        platform: str,
        video_path: Optional[Path] = None,
    ) -> str:
        if formats:
            markdown = self.apply_format_markers(
                markdown=markdown,
                video_path=video_path,
                formats=formats,
                audio_meta=audio_meta,
                platform=platform,
            )
        return prepend_source_link(markdown, video_url)

    def apply_format_markers(
        self,
        markdown: str,
        video_path: Optional[Path],
        formats: List[str],
        audio_meta: AudioDownloadResult,
        platform: str,
    ) -> str:
        if "screenshot" in formats and video_path:
            try:
                processed = self.insert_screenshots(markdown, video_path)
                if processed is not None:
                    markdown = processed
            except Exception:
                logger.warning("截图插入失败，跳过该步骤")

        if "link" in formats:
            try:
                markdown = replace_content_markers(markdown, video_id=audio_meta.video_id, platform=platform)
            except Exception as exc:
                logger.warning(f"链接插入失败，跳过该步骤：{exc}")

        return markdown

    def insert_screenshots(self, markdown: str, video_path: Path) -> str | None:
        matches = extract_screenshot_timestamps(markdown)
        for idx, (marker, ts) in enumerate(matches):
            try:
                img_path = generate_screenshot(str(video_path), str(self.image_output_dir), ts, idx)
                filename = Path(img_path).name
                img_url = f"{self.image_base_url.rstrip('/')}/{filename}"
                markdown = markdown.replace(marker, f"![]({img_url})", 1)
            except Exception as exc:
                logger.error(f"生成截图失败 (timestamp={ts})：{exc}")
                return None
        return markdown
