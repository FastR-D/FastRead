from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Literal, Optional
import os

from app.services.chat_service import chat as chat_service
from app.services.vector_store import VectorStoreManager
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R
from app.utils.local_access import require_local_request
from app.validators.task_id_validator import CanonicalTaskId

logger = get_logger(__name__)
CHAT_VECTOR_INDEX_ENABLED = os.getenv("CHAT_VECTOR_INDEX_ENABLED", "0").lower() in {"1", "true", "yes", "on"}

router = APIRouter(dependencies=[Depends(require_local_request)])

# 索引状态追踪: task_id -> "indexing" | "indexed" | "failed"
_index_status: dict[str, str] = {}


class IndexRequest(BaseModel):
    task_id: CanonicalTaskId


class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    task_id: Optional[CanonicalTaskId] = None
    scope: Literal["task", "library"] = "task"
    question: str
    history: list[ChatMessage] = []
    provider_id: str
    model_name: str


def _do_index(task_id: str):
    """后台执行索引任务。"""
    try:
        _index_status[task_id] = "indexing"
        store = VectorStoreManager()
        store.index_task(task_id)
        if store.is_indexed(task_id):
            _index_status[task_id] = "indexed"
            logger.info(f"索引完成: {task_id}")
        else:
            _index_status[task_id] = "failed"
            logger.warning(f"索引未生成有效 collection: {task_id}")
    except Exception as e:
        _index_status[task_id] = "failed"
        logger.error(f"索引失败: {task_id}, {e}")


@router.post("/chat/index")
def index_task(data: IndexRequest, background_tasks: BackgroundTasks):
    """触发后台索引，立即返回。"""
    if not CHAT_VECTOR_INDEX_ENABLED:
        _index_status[data.task_id] = "disabled"
        return R.success(
            msg="向量索引默认关闭，当前使用基础检索",
            data={"status": "disabled", "indexed": False},
        )

    if _index_status.get(data.task_id) == "indexing":
        return R.success(msg="正在索引中")

    # 如果已经索引过，直接返回；不可用时允许前端走基础检索模式。
    try:
        store = VectorStoreManager()
        if store.is_indexed(data.task_id):
            _index_status[data.task_id] = "indexed"
            return R.success(msg="已完成索引")
    except Exception as e:
        _index_status[data.task_id] = "failed"
        logger.warning(f"索引组件不可用，跳过向量索引: {e}")
        return R.success(msg="索引组件不可用，已使用基础检索", data={"status": "failed"})

    _index_status[data.task_id] = "indexing"
    background_tasks.add_task(_do_index, data.task_id)
    return R.success(msg="开始索引")


@router.get("/chat/status")
def chat_status(task_id: CanonicalTaskId):
    """返回索引状态：disabled / idle / indexing / indexed / failed。"""
    if not CHAT_VECTOR_INDEX_ENABLED:
        return R.success(data={"status": "disabled", "indexed": False})

    try:
        # 优先检查内存状态
        status = _index_status.get(task_id)
        if status:
            return R.success(data={"status": status, "indexed": status == "indexed"})

        # 内存没有记录，检查持久化
        store = VectorStoreManager()
        indexed = store.is_indexed(task_id)
        if indexed:
            _index_status[task_id] = "indexed"
        return R.success(data={"status": "indexed" if indexed else "idle", "indexed": indexed})
    except Exception as e:
        logger.error(f"查询索引状态失败: {e}")
        return R.success(data={"status": "idle", "indexed": False})


@router.post("/chat/ask")
def ask_question(data: AskRequest):
    """基于论文分页原文的问答。"""
    try:
        if data.scope == "task" and not data.task_id:
            return R.error(msg="当前论文问答需要 task_id")
        history = [{"role": m.role, "content": m.content} for m in data.history]
        result = chat_service(
            task_id=data.task_id,
            question=data.question,
            history=history,
            provider_id=data.provider_id,
            model_name=data.model_name,
            scope=data.scope,
        )
        return R.success(data=result)
    except ValueError as e:
        return R.error(msg=str(e))
    except Exception as e:
        logger.error(f"Chat 问答失败: {e}", exc_info=True)
        return R.error(msg=f"问答失败: {str(e)}")
