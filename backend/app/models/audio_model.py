from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioDownloadResult:
    file_path: str               # 本地音频路径
    title: str                   # 视频标题
    duration: float              # 视频时长（秒）
    cover_url: Optional[str]     # 视频封面图
    platform: str                # 平台，当前为 "douyin"
    video_id: str                # 唯一视频ID
    raw_info: dict               # 平台原始元信息
    video_path: Optional[str] = None  #  新增字段：可选视频文件路径
