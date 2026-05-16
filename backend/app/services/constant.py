from app.downloaders.douyin_downloader import DouyinDownloader
from app.downloaders.yt_dlp_downloader import YtDlpDownloader

SUPPORT_PLATFORM_MAP = {
    'douyin': DouyinDownloader(),
    'bilibili': YtDlpDownloader('bilibili'),
    'kuaishou': YtDlpDownloader('kuaishou'),
}
