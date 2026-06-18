import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from app.core.settings import get_settings
from app.db.init_db import init_db
from app.db.provider_dao import seed_default_providers
from app.exceptions.exception_handlers import register_exception_handlers
# from app.db.model_dao import init_model_table
# from app.db.provider_dao import init_provider_table
from app.utils.logger import get_logger
from app import create_app
from app.services.transcriber_config_manager import TranscriberConfigManager
from events import register_handler
from ffmpeg_helper import ensure_ffmpeg_or_raise

logger = get_logger(__name__)
settings = get_settings()
settings.ensure_runtime_dirs()

@asynccontextmanager
async def lifespan(app: FastAPI):
    register_handler()
    init_db()
    # 转写器不再在启动时强制初始化，而是在首次生成笔记时按需创建
    # 如果配置了不可用的类型（如 mlx-whisper 未安装），会在使用时报错而非静默回退
    _cfg = TranscriberConfigManager().get_config()
    logger.info(f"当前转写器配置: type={_cfg['transcriber_type']}, model_size={_cfg['whisper_model_size']}")
    seed_default_providers()
    yield

app = create_app(lifespan=lifespan)

# 允许的源：本地 web 端 + Tauri 桌面端 + 浏览器扩展（chrome/edge/firefox）
# 用 regex 是因为 chrome-extension://<id> 的 id 在每次开发版加载时不固定
CORS_ORIGIN_REGEX = (
    r"^chrome-extension://[a-z]+$"
    r"|^moz-extension://.+$"
    r"|^http://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|^http://tauri\.localhost$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
register_exception_handlers(app)
app.mount(settings.static_path, StaticFiles(directory=settings.static_dir), name="static")
app.mount(settings.uploads_path, StaticFiles(directory=settings.uploads_dir), name="uploads")









if __name__ == "__main__":
    port = settings.backend_port
    host = settings.backend_host
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=False)
