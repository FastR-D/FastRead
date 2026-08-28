import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles

from app.core.settings import get_settings
from app.db.init_db import init_db
from app.db.provider_dao import migrate_provider_secrets, seed_default_providers
from app.exceptions.exception_handlers import register_exception_handlers
# from app.db.model_dao import init_model_table
# from app.db.provider_dao import init_provider_table
from app.utils.logger import get_logger
from app.utils.local_access import LocalOnlyASGI
from app import create_app
from app.services.task_recovery_service import recover_interrupted_tasks

logger = get_logger(__name__)
settings = get_settings()
settings.ensure_runtime_dirs()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    recovered = recover_interrupted_tasks()
    if recovered:
        logger.warning(f"已将 {len(recovered)} 个重启前未完成任务标记为可重试失败")
    seed_default_providers()
    migrate_provider_secrets()
    yield

app = create_app(lifespan=lifespan)

# Local web and Tauri desktop origins.
CORS_ORIGIN_REGEX = (
    r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
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
app.mount(
    settings.uploads_path,
    LocalOnlyASGI(StaticFiles(directory=settings.uploads_dir)),
    name="uploads",
)

if __name__ == "__main__":
    port = settings.backend_port
    host = settings.backend_host
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=False)
