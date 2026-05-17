from pydantic import AnyUrl, BaseModel, field_validator, model_validator
import re
from urllib.parse import urlparse

SUPPORTED_PLATFORMS = {
    "douyin": r"https?://[^/\s]*douyin\.com/\S+",
    "bilibili": r"https?://[^/\s]*(bilibili\.com|b23\.tv)/\S+",
    "kuaishou": r"https?://[^/\s]*(kuaishou\.com|chenzhongtech\.com)/\S+",
}


def is_supported_video_url(url: str, platform: str | None = None) -> bool:
    patterns = [SUPPORTED_PLATFORMS.get(platform)] if platform else SUPPORTED_PLATFORMS.values()
    match = next((re.search(pattern, url) for pattern in patterns if pattern), None)
    if not match:
        return False

    parsed = urlparse(match.group(0))
    hostname = parsed.hostname or ""
    allowed_hosts = {
        "douyin": ("douyin.com",),
        "bilibili": ("bilibili.com", "b23.tv"),
        "kuaishou": ("kuaishou.com", "chenzhongtech.com"),
    }
    platforms = [platform] if platform else list(allowed_hosts)
    return any(
        any(hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts[item])
        for item in platforms
        if item in allowed_hosts
    )


class VideoRequest(BaseModel):
    url: AnyUrl
    platform: str

    @field_validator("platform")
    def validate_platform(cls, v):
        if v not in SUPPORTED_PLATFORMS:
            raise ValueError("当前仅支持抖音精选、B站、快手视频")
        return v

    @field_validator("url")
    def validate_video_url(cls, v):
        if not is_supported_video_url(str(v)):
            raise ValueError("请输入支持平台的视频链接")
        return v

    @model_validator(mode="after")
    def validate_platform_url(self):
        if not is_supported_video_url(str(self.url), self.platform):
            raise ValueError("链接与所选平台不匹配")
        return self
