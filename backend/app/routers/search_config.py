from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.search_connection_config import (
    get_search_connection_config,
    save_search_connection_config,
)
from app.utils.local_access import require_local_request
from app.utils.response import ResponseWrapper as R


router = APIRouter(dependencies=[Depends(require_local_request)])


class SearchConnectionConfigRequest(BaseModel):
    paper_search_proxy_url: str = ""
    google_scholar_api_url: str = ""
    serpapi_api_key: str | None = None
    clear_serpapi_api_key: bool = False
    elasticsearch_url: str = ""


@router.get("/paper_search_config")
def get_paper_search_config():
    return R.success(data=get_search_connection_config().public_dict())


@router.put("/paper_search_config")
def update_paper_search_config(data: SearchConnectionConfigRequest):
    try:
        config = save_search_connection_config(**data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return R.success(msg="学术检索连接设置已保存", data=config.public_dict())
