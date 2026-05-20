import json
import os
import re
from typing import Optional

from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.gpt_provider import GPTProvider
from app.services.vector_store import VectorStoreManager
from app.services.chat_tools import TOOLS, execute_tool
from app.utils.logger import get_logger

logger = get_logger(__name__)

ARTIFACTS = NoteArtifactRepository()
CHAT_VECTOR_INDEX_ENABLED = os.getenv("CHAT_VECTOR_INDEX_ENABLED", "0").lower() in {"1", "true", "yes", "on"}

SYSTEM_PROMPT = """你是一个视频笔记问答助手。你拥有以下能力：

1. 系统已自动检索了一些相关内容作为初始参考（见下方）
2. 你可以调用工具主动查询更多信息：
   - lookup_transcript: 查询视频原始转录文本（支持按时间、关键词、位置筛选）
   - get_video_info: 获取视频元信息（标题、作者、简介、标签等）
   - get_note_content: 获取完整笔记内容

--- 初始检索内容 ---
{context}
---

回答要求：
- 如果初始检索内容不足以回答问题，请主动调用工具获取更多信息
- 回答关于视频具体原话、细节时，用 lookup_transcript 查询原文
- 回答关于作者、标题等基本信息时，用 get_video_info 查询
- 请用中文回答，保持简洁准确"""

LIBRARY_SYSTEM_PROMPT = """你是一个跨视频知识库问答助手。

系统会提供多个视频笔记中召回的相关片段。请综合这些片段回答用户问题。

--- 知识库检索内容 ---
{context}
---

回答要求：
- 优先综合多个视频之间的共同结论、差异和可执行建议
- 如果证据不足，请明确说明不足，不要编造视频里没有的信息
- 提到关键观点时，尽量指出来自哪个视频标题
- 请用中文回答，保持简洁准确"""


def _build_context(chunks: list[dict]) -> str:
    """将检索到的片段拼接为上下文文本。"""
    parts = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        source_type = meta.get("source_type", "unknown")
        if source_type == "meta":
            label = "[视频信息]"
        elif source_type == "markdown":
            label = f"[笔记 - {meta.get('section_title', '')}]"
        else:
            start = meta.get("start_time", 0)
            end = meta.get("end_time", 0)
            if meta.get("title"):
                label = f"[转录 - {meta.get('title')}]"
            else:
                label = f"[转录 - {start:.0f}s~{end:.0f}s]"
        if meta.get("title") and source_type != "transcript":
            label = f"{label} {meta.get('title')}"
        parts.append(f"{label}\n{chunk['text']}")
    return "\n\n".join(parts)


def _build_sources(chunks: list[dict]) -> list[dict]:
    """从检索片段中提取来源信息。"""
    sources = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        source = {
            "text": chunk["text"][:200],
            "source_type": meta.get("source_type", "unknown"),
        }
        if meta.get("task_id"):
            source["task_id"] = meta["task_id"]
        if meta.get("title"):
            source["title"] = meta["title"]
        if meta.get("section_title"):
            source["section_title"] = meta["section_title"]
        if meta.get("start_time") is not None:
            source["start_time"] = meta["start_time"]
        if meta.get("end_time") is not None:
            source["end_time"] = meta["end_time"]
        sources.append(source)
    return sources


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    words = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    grams = [chinese[i:i + 2] for i in range(max(len(chinese) - 1, 0))]
    return words + grams


def _chunk_text(text: str, size: int = 520, overlap: int = 80) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    chunks = []
    step = max(size - overlap, 1)
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start:start + size].strip()
        if len(chunk) >= 30:
            chunks.append(chunk)
        if start + size >= len(cleaned):
            break
    return chunks


def _load_library_chunks() -> list[dict]:
    chunks = []
    for result_file in ARTIFACTS.iter_result_files():
        task_id = result_file.task_id
        note_data = ARTIFACTS.read_result(task_id)
        if not note_data:
            logger.warning(f"读取知识库笔记失败: {result_file.path.name}")
            continue

        audio_meta = note_data.get("audio_meta") or {}
        raw_info = audio_meta.get("raw_info") or {}
        title = audio_meta.get("title") or task_id
        markdown = note_data.get("markdown") or ""
        transcript = note_data.get("transcript") or {}
        transcript_text = transcript.get("full_text") or ""
        tags = raw_info.get("tags") if isinstance(raw_info.get("tags"), list) else []
        meta_text = "\n".join(part for part in [
            f"视频标题：{title}",
            f"平台：{audio_meta.get('platform', '')}",
            f"标签：{', '.join(str(tag) for tag in tags[:12])}" if tags else "",
        ] if part.strip("：, "))

        for source_type, source_text in (
            ("meta", meta_text),
            ("markdown", markdown),
            ("transcript", transcript_text),
        ):
            for index, text in enumerate(_chunk_text(source_text)):
                chunks.append({
                    "text": text,
                    "metadata": {
                        "task_id": task_id,
                        "title": title,
                        "source_type": source_type,
                        "chunk_index": index,
                    },
                })

    return chunks


def _load_task_data(task_id: str) -> Optional[dict]:
    return ARTIFACTS.read_result(task_id)


def _normalize_markdown(markdown) -> str:
    if isinstance(markdown, list):
        if not markdown:
            return ""
        latest = markdown[0] if isinstance(markdown[0], dict) else markdown[-1]
        if isinstance(latest, dict):
            return latest.get("content", "") or ""
        return str(latest)
    return markdown or ""


def _load_task_chunks(task_id: str) -> list[dict]:
    note_data = _load_task_data(task_id)
    if not note_data:
        return []

    audio_meta = note_data.get("audio_meta") or {}
    raw_info = audio_meta.get("raw_info") or {}
    title = audio_meta.get("title") or task_id
    markdown = _normalize_markdown(note_data.get("markdown"))
    transcript = note_data.get("transcript") or {}
    transcript_text = transcript.get("full_text") or ""
    tags = raw_info.get("tags") if isinstance(raw_info.get("tags"), list) else []
    meta_text = "\n".join(part for part in [
        f"视频标题：{title}",
        f"平台：{audio_meta.get('platform', '')}",
        f"作者：{raw_info.get('uploader', '')}",
        f"简介：{str(raw_info.get('description', ''))[:500]}" if raw_info.get("description") else "",
        f"标签：{', '.join(str(tag) for tag in tags[:12])}" if tags else "",
    ] if part.strip("：, "))

    chunks = []
    for source_type, source_text in (
        ("meta", meta_text),
        ("markdown", markdown),
        ("transcript", transcript_text),
    ):
        for index, text in enumerate(_chunk_text(source_text)):
            chunks.append({
                "text": text,
                "metadata": {
                    "task_id": task_id,
                    "title": title,
                    "source_type": source_type,
                    "chunk_index": index,
                },
            })
    return chunks


def _rank_chunks(chunks: list[dict], question: str, n_results: int) -> list[dict]:
    query_terms = _tokenize(question)
    if not query_terms:
        return chunks[:n_results]
    query_set = set(query_terms)
    ranked = []
    for chunk in chunks:
        text = chunk["text"]
        terms = _tokenize(text)
        if not terms:
            continue
        meta = chunk.get("metadata", {})
        title = meta.get("title", "")
        source_type = meta.get("source_type", "")
        overlap = len(query_set & set(terms))
        title_overlap = len(query_set & set(_tokenize(title)))
        score = overlap * 3 + title_overlap * 5
        if source_type == "meta":
            score += 1
        lower_text = text.lower()
        for term in query_set:
            if term and term in lower_text:
                score += 2
        if score > 0:
            ranked.append((score, chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked[:n_results]]


def _query_task_fallback(task_id: str, question: str, n_results: int = 6) -> list[dict]:
    return _rank_chunks(_load_task_chunks(task_id), question, n_results)


def _query_library(question: str, n_results: int = 8) -> list[dict]:
    return _rank_chunks(_load_library_chunks(), question, n_results)


def _get_gpt(provider_id: str, model_name: str):
    return GPTProvider.create(provider_id=provider_id, model_name=model_name)


def library_chat(
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
) -> dict:
    chunks = _query_library(question, n_results=8)
    context = _build_context(chunks) if chunks else "（未从知识库中检索到相关内容）"
    sources = _build_sources(chunks) if chunks else []

    messages = [{"role": "system", "content": LIBRARY_SYSTEM_PROMPT.format(context=context)}]
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    gpt = _get_gpt(provider_id, model_name)
    logger.info(f"Library Chat: model={model_name}, chunks={len(chunks)}")
    response = gpt.client.chat.completions.create(
        model=gpt.model,
        messages=messages,
        temperature=0.7,
    )
    return {"answer": response.choices[0].message.content or "", "sources": sources}


def chat(
    task_id: Optional[str],
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
    scope: str = "task",
) -> dict:
    """
    RAG + Tool Calling 问答。
    1. 向量检索初始上下文
    2. 调用 LLM（带 tools）
    3. 如果 LLM 调用了工具，执行工具并将结果返回给 LLM
    4. 循环直到 LLM 给出最终回答
    """
    if scope == "library":
        return library_chat(question, history, provider_id, model_name)
    if not task_id:
        raise ValueError("当前视频问答需要 task_id")

    # 1. 检索初始上下文：默认使用笔记 JSON 关键词检索，避免 Chroma 首次下载 embedding 模型阻塞问答。
    chunks = []
    if CHAT_VECTOR_INDEX_ENABLED:
        try:
            vector_store = VectorStoreManager()
            chunks = vector_store.query(task_id, question, n_results=6)
        except Exception as exc:
            logger.warning(f"向量检索不可用，降级为文件检索: task_id={task_id}, {exc}")

    if not chunks:
        chunks = _query_task_fallback(task_id, question, n_results=6)

    context = _build_context(chunks) if chunks else "（未检索到相关内容，请使用工具查询）"
    sources = _build_sources(chunks) if chunks else []

    # 2. 构建消息
    system_msg = SYSTEM_PROMPT.format(context=context)
    messages = [{"role": "system", "content": system_msg}]

    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})

    # 3. 获取 LLM client
    gpt = _get_gpt(provider_id, model_name)

    logger.info(f"Chat: task_id={task_id}, model={model_name}")

    # 4. Tool calling 循环（最多 3 轮）
    max_rounds = 3
    for round_i in range(max_rounds):
        try:
            response = gpt.client.chat.completions.create(
                model=gpt.model,
                messages=messages,
                tools=TOOLS,
                temperature=0.7,
            )
        except Exception as exc:
            logger.warning(f"模型不支持工具调用或工具调用失败，退回普通问答: {exc}")
            response = gpt.client.chat.completions.create(
                model=gpt.model,
                messages=messages,
                temperature=0.7,
            )
            return {"answer": response.choices[0].message.content or "", "sources": sources}

        msg = response.choices[0].message

        # 没有工具调用，直接返回
        if not msg.tool_calls:
            return {"answer": msg.content or "", "sources": sources}

        # 处理工具调用
        messages.append(msg)

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            logger.info(f"Tool call [{round_i+1}/{max_rounds}]: {fn_name}({fn_args})")

            result = execute_tool(task_id, fn_name, fn_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    # 超过最大轮次，做最后一次不带 tools 的调用
    response = gpt.client.chat.completions.create(
        model=gpt.model,
        messages=messages,
        temperature=0.7,
    )

    return {"answer": response.choices[0].message.content or "", "sources": sources}
