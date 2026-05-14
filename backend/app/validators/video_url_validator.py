from pydantic import AnyUrl, BaseModel, field_validator
import re
from urllib.parse import urlparse

SUPPORTED_PLATFORMS = {
    "douyin": r"https?://[^/\s]*douyin\.com/\S+",
}


def is_supported_video_url(url: str) -> bool:
    match = re.search(SUPPORTED_PLATFORMS["douyin"], url)
    if not match:
        return False

    parsed = urlparse(match.group(0))
    hostname = parsed.hostname or ""
    return hostname == "douyin.com" or hostname.endswith(".douyin.com")


class VideoRequest(BaseModel):
    url: AnyUrl
    platform: str

    @field_validator("platform")
    def validate_platform(cls, v):
        if v != "douyin":
            raise ValueError("当前仅支持抖音精选视频")
        return v

    @field_validator("url")
    def validate_video_url(cls, v):
        if not is_supported_video_url(str(v)):
            raise ValueError("请输入抖音精选视频链接")
        return v
