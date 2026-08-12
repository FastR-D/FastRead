from fastapi import APIRouter

from app.utils.response import ResponseWrapper as R

router = APIRouter()


@router.get("/sys_health")
async def sys_health():
    return R.success()


@router.get("/sys_check")
async def sys_check():
    return R.success()
