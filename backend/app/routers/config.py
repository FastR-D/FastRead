from __future__ import annotations

import os
import platform
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.settings import get_settings
from app.db.engine import get_engine
from app.utils.local_access import require_local_request
from app.utils.response import ResponseWrapper as R


router = APIRouter(dependencies=[Depends(require_local_request)])
settings = get_settings()


def _runtime_checks() -> tuple[dict, list[str]]:
    checks = {"database": False, "paper_storage": False, "uploads": False}
    errors: list[str] = []
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        errors.append(f"database: {str(exc)[:160]}")

    for key, directory in (
        ("paper_storage", settings.paper_output_dir),
        ("uploads", settings.uploads_dir),
    ):
        try:
            Path(directory).mkdir(parents=True, exist_ok=True)
            checks[key] = os.access(directory, os.R_OK | os.W_OK)
            if not checks[key]:
                errors.append(f"{key}: directory is not readable and writable")
        except Exception as exc:
            errors.append(f"{key}: {str(exc)[:160]}")
    return checks, errors


@router.get("/sys_health")
async def sys_health():
    checks, errors = _runtime_checks()
    if errors:
        return R.error(msg="；".join(errors), code=503)
    return R.success(data={"status": "healthy", "checks": checks, "errors": []})


@router.get("/sys_check")
async def sys_check():
    checks, errors = _runtime_checks()
    return R.success(data={"checks": checks, "errors": errors})


@router.get("/deploy_status")
async def deploy_status():
    checks, errors = _runtime_checks()
    return R.success(
        data={
            "backend": {"status": "running", "port": settings.backend_port},
            "database": {
                "path": str(settings.sqlite_db_path),
                "available": checks["database"],
            },
            "storage": {
                "paper_results": checks["paper_storage"],
                "uploads": checks["uploads"],
            },
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "errors": errors,
        }
    )
