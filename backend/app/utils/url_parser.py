import re
from typing import Optional


def extract_video_id(url: str, platform: str) -> Optional[str]:
    """
    从抖音链接中提取视频 ID

    :param url: 视频链接
    :param platform: 平台名；当前仅支持 douyin
    :return: 提取到的视频 ID 或 None
    """
    if platform != "douyin":
        return None

    match = re.search(r"/video/(\d+)", url)
    if match:
        return match.group(1)

    match = re.search(r"(?:modal_id|aweme_id)=(\d+)", url)
    if match:
        return match.group(1)

    match = re.search(r"/(\d{16,})", url)
    if match:
        return match.group(1)
    return None
