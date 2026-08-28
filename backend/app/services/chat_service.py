from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Optional

from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.gpt_provider import GPTProvider
from app.services.llm_compat import create_chat_completion
from app.services.vector_store import VectorStoreManager
from app.utils.logger import get_logger


logger = get_logger(__name__)
ARTIFACTS = PaperArtifactRepository()
CHAT_VECTOR_INDEX_ENABLED = os.getenv("CHAT_VECTOR_INDEX_ENABLED", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

PAPER_SYSTEM_PROMPT = """你是 FastRead 的单篇论文阅读问答助手。
只能依据下面给出的论文分页原文回答，不能使用模型记忆补写事实，也不能把单篇论文陈述升级成领域共识。
每个实质结论必须引用当前上下文中的页码和逐字短引文；证据不足时回答“原文证据不足”。

论文原文：
{context}

只返回 JSON：
{{"answer":"中文回答","citations":[{{"page":1,"exact_quote":"逐字短引文"}}]}}
"""

LIBRARY_SYSTEM_PROMPT = """你是 FastRead 的论文资料库问答助手。
只能综合下面给出的多篇论文分页原文；必须用 [S1]、[S2] 标明来源，不得使用模型记忆补写。
证据不足时明确说明，不要伪造共识。

分页原文：
{context}
"""


def _tokens(text: str) -> list[str]:
    lowered = str(text or "").lower()
    words = re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", lowered)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    return words + [chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))]


def _chunk_page(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start : start + size].strip()
        if len(chunk) >= 30:
            chunks.append(chunk)
        if start + size >= len(cleaned):
            break
    return chunks


def _paper_chunks(task_id: str, payload: dict) -> list[dict]:
    document = payload.get("paper_document") or {}
    title = str(document.get("title") or task_id)
    chunks: list[dict] = []
    for page in document.get("pages") or []:
        page_number = int(page.get("page") or 1)
        for index, text in enumerate(_chunk_page(page.get("text") or "")):
            chunks.append(
                {
                    "text": text,
                    "metadata": {
                        "task_id": task_id,
                        "title": title,
                        "source_type": "paper_page",
                        "page_start": page_number,
                        "page_end": page_number,
                        "chunk_index": index,
                        "source_url": document.get("pdf_url") or document.get("source_url") or "",
                        "doi": document.get("doi") or "",
                    },
                }
            )
    return chunks


def _rank(chunks: list[dict], question: str, limit: int) -> list[dict]:
    query_counts = Counter(_tokens(question))
    if not query_counts:
        return chunks[:limit]
    ranked = []
    for chunk in chunks:
        counts = Counter(_tokens(chunk.get("text") or ""))
        score = sum(min(counts[token], count) for token, count in query_counts.items())
        if score:
            ranked.append((score, chunk))
    ranked.sort(
        key=lambda item: (
            -item[0],
            int((item[1].get("metadata") or {}).get("page_start") or 0),
        )
    )
    return [chunk for _, chunk in ranked[:limit]]


def _load_task(task_id: str) -> dict:
    payload = ARTIFACTS.read_result(task_id)
    if not payload or payload.get("paper_task") is not True:
        raise ValueError("论文任务不存在")
    return payload


def _task_chunks(task_id: str, question: str, limit: int = 6) -> tuple[dict, list[dict]]:
    payload = _load_task(task_id)
    chunks: list[dict] = []
    if CHAT_VECTOR_INDEX_ENABLED:
        try:
            chunks = [
                chunk
                for chunk in VectorStoreManager().query(task_id, question, n_results=limit)
                if (chunk.get("metadata") or {}).get("source_type") == "paper_page"
            ]
        except Exception as exc:
            logger.warning(f"向量检索不可用，使用本地分页检索: {exc}")
    if not chunks:
        chunks = _rank(_paper_chunks(task_id, payload), question, limit)
    return payload, chunks


def _library_chunks(question: str, limit: int = 10) -> list[dict]:
    chunks: list[dict] = []
    for result_file in ARTIFACTS.iter_result_files() or []:
        payload = ARTIFACTS.read_result(result_file.task_id)
        if payload and payload.get("paper_task") is True:
            chunks.extend(_paper_chunks(result_file.task_id, payload))
    return _rank(chunks, question, limit)


def _context(chunks: list[dict], *, source_labels: bool = False) -> str:
    lines = []
    for index, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata") or {}
        label = f"[S{index}] " if source_labels else ""
        lines.append(
            f"{label}[{metadata.get('title', '')} · 第 {metadata.get('page_start', '?')} 页]\n"
            f"{chunk.get('text', '')}"
        )
    return "\n\n".join(lines)


def _source_records(chunks: list[dict]) -> list[dict]:
    records = []
    for index, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata") or {}
        records.append(
            {
                "source_id": f"S{index}",
                "source_type": "paper_page",
                "task_id": metadata.get("task_id") or "",
                "title": metadata.get("title") or "",
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
                "source_url": metadata.get("source_url") or "",
                "doi": metadata.get("doi") or "",
            }
        )
    return records


def _strip_fence(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _ground_task_answer(raw: str, payload: dict, chunks: list[dict]) -> dict:
    try:
        parsed = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        return {"answer": "原文证据不足", "sources": [], "grounding_status": "citation_rejected"}
    if not isinstance(parsed, dict):
        return {"answer": "原文证据不足", "sources": [], "grounding_status": "citation_rejected"}
    answer = str(parsed.get("answer") or "").strip()
    citations = parsed.get("citations") if isinstance(parsed.get("citations"), list) else []
    pages = {
        int(page.get("page") or 1): str(page.get("text") or "")
        for page in (payload.get("paper_document") or {}).get("pages") or []
    }
    allowed_pages = {
        int((chunk.get("metadata") or {}).get("page_start") or 0) for chunk in chunks
    }
    sources = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        try:
            page_number = int(citation.get("page"))
        except (TypeError, ValueError):
            continue
        quote = re.sub(r"\s+", " ", str(citation.get("exact_quote") or "")).strip()
        page_text = re.sub(r"\s+", " ", pages.get(page_number, ""))
        if page_number not in allowed_pages or len(quote) < 8 or quote.casefold() not in page_text.casefold():
            continue
        document = payload.get("paper_document") or {}
        sources.append(
            {
                "source_type": "paper_page",
                "task_id": document.get("id") or "",
                "title": document.get("title") or "",
                "page_start": page_number,
                "page_end": page_number,
                "exact_quote": quote,
                "source_url": document.get("pdf_url") or document.get("source_url") or "",
            }
        )
    if not answer or not sources:
        return {"answer": "原文证据不足", "sources": [], "grounding_status": "citation_rejected"}
    return {"answer": answer, "sources": sources, "grounding_status": "source_grounded"}


def _get_gpt(provider_id: str, model_name: str):
    return GPTProvider.create(provider_id=provider_id, model_name=model_name)


def chat(
    task_id: Optional[str],
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
    scope: str = "task",
) -> dict:
    if scope == "library":
        chunks = _library_chunks(question)
        context = _context(chunks, source_labels=True) if chunks else "（未找到相关分页原文）"
        messages = [{"role": "system", "content": LIBRARY_SYSTEM_PROMPT.format(context=context)}]
        messages.extend(history[-20:])
        messages.append({"role": "user", "content": question})
        gpt = _get_gpt(provider_id, model_name)
        response = create_chat_completion(
            gpt.client,
            model=gpt.model,
            messages=messages,
            temperature=0.3,
        )
        return {
            "answer": response.choices[0].message.content or "",
            "sources": _source_records(chunks),
            "grounding_status": "source_context_supplied" if chunks else "insufficient_source",
        }

    if not task_id:
        raise ValueError("当前论文问答需要 task_id")
    payload, chunks = _task_chunks(task_id, question)
    context = _context(chunks) if chunks else "（未找到相关分页原文）"
    messages = [{"role": "system", "content": PAPER_SYSTEM_PROMPT.format(context=context)}]
    messages.extend(history[-20:])
    messages.append({"role": "user", "content": question})
    gpt = _get_gpt(provider_id, model_name)
    response = create_chat_completion(
        gpt.client,
        model=gpt.model,
        messages=messages,
        temperature=0.2,
    )
    return _ground_task_answer(response.choices[0].message.content or "", payload, chunks)
