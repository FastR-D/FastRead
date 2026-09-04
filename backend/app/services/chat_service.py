from __future__ import annotations

import json
import re
from collections import Counter
from typing import Optional

from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.gpt_provider import GPTProvider
from app.services.llm_compat import create_chat_completion
from app.services.vector_store import VectorStoreManager, vector_index_capability
from app.utils.logger import get_logger


logger = get_logger(__name__)
ARTIFACTS = PaperArtifactRepository()

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


def _rank_matches(chunks: list[dict], question: str) -> list[dict]:
    query_counts = Counter(_tokens(question))
    if not query_counts:
        return list(chunks)
    ranked: list[tuple[int, int, int, dict]] = []
    for chunk in chunks:
        counts = Counter(_tokens(chunk.get("text") or ""))
        # Repeated mentions usually indicate the page that explains a concept,
        # not a page that merely names it. Cap the bonus to avoid long pages
        # overwhelming every other signal.
        score = sum(
            min(counts[token], max(1, count) * 3)
            for token, count in query_counts.items()
        )
        if score:
            metadata = chunk.get("metadata") or {}
            ranked.append(
                (
                    score,
                    int(metadata.get("page_start") or 0),
                    int(metadata.get("chunk_index") or 0),
                    chunk,
                )
            )
    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1],
            item[2],
        )
    )

    # First keep the best chunk from every matching page. This prevents six
    # chunks from an early page from hiding later pages that also contain the
    # requested concept. Fill remaining slots with the next-best chunks.
    selected: list[dict] = []
    selected_ids: set[tuple[int, int]] = set()
    seen_pages: set[int] = set()
    for _, page_number, chunk_index, chunk in ranked:
        if page_number in seen_pages:
            continue
        seen_pages.add(page_number)
        selected_ids.add((page_number, chunk_index))
        selected.append(chunk)
    for _, page_number, chunk_index, chunk in ranked:
        identity = (page_number, chunk_index)
        if identity not in selected_ids:
            selected_ids.add(identity)
            selected.append(chunk)
    return selected


def _rank(chunks: list[dict], question: str, limit: int) -> list[dict]:
    return _rank_matches(chunks, question)[:limit]


_CONTEXTUAL_QUESTION_RE = re.compile(
    r"(?:这个|该(?:阶段|方法|结论|实验|机制)|它们?|上述|前者|后者|这一|这些|那一|这种|"
    r"\b(?:this|that|it|they|them|former|latter)\b)",
    re.IGNORECASE,
)


def _retrieval_query(question: str, history: list[dict] | None = None) -> str:
    """Make anaphoric follow-ups searchable without trusting chat as evidence."""
    current = re.sub(r"\s+", " ", str(question or "")).strip()
    if not history:
        return current
    needs_context = bool(_CONTEXTUAL_QUESTION_RE.search(current)) or len(_tokens(current)) <= 4
    if not needs_context:
        return current

    hints: list[str] = []
    for message in history[-6:]:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            continue
        content = re.sub(r"\s+", " ", str(message.get("content") or "")).strip()
        if content:
            hints.append(content[:600])
    return " ".join([*hints[-4:], current]).strip()


def _explicit_page_numbers(question: str) -> list[int]:
    pages: set[int] = set()
    pattern = (
        r"(?:第\s*)?(\d{1,4})(?:\s*[/、和及]\s*(?:第\s*)?(\d{1,4}))?\s*页"
        r"|\bpages?\s*(\d{1,4})(?:\s*[-–]\s*(\d{1,4}))?\b"
    )
    for match in re.finditer(pattern, question, re.IGNORECASE):
        for value in match.groups():
            if value:
                pages.add(int(value))
    return sorted(pages)


def _report_hint_chunks(
    payload: dict,
    chunks: list[dict],
    question: str,
    limit: int,
) -> list[dict]:
    """Bridge cross-language questions through already grounded report evidence."""
    report = (payload.get("insights") or {}).get("reading_report") or {}
    query_counts = Counter(_tokens(question))
    if not query_counts or not report:
        return []

    entries: list[tuple[int, list[dict]]] = []

    def add_entry(text: str, evidence) -> None:
        if not isinstance(evidence, list):
            return
        text_counts = Counter(_tokens(text))
        score = sum(min(text_counts[token], count) for token, count in query_counts.items())
        grounded = [item for item in evidence if isinstance(item, dict) and item.get("page_start")]
        if score and grounded:
            entries.append((score, grounded))

    for item in report.get("key_questions") or []:
        if isinstance(item, dict):
            add_entry(
                " ".join(
                    str(item.get(field) or "")
                    for field in ("question", "answer", "why_it_matters")
                ),
                item.get("evidence"),
            )
    for item in report.get("process") or []:
        if isinstance(item, dict):
            add_entry(
                f"{item.get('step') or ''} {item.get('description') or ''}",
                item.get("evidence"),
            )
    for item in report.get("contributions") or []:
        if isinstance(item, dict):
            add_entry(
                f"{item.get('title') or ''} {item.get('description') or ''}",
                item.get("evidence"),
            )

    selected: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for _, evidence_items in sorted(entries, key=lambda item: -item[0]):
        for evidence in evidence_items:
            page_number = int(evidence.get("page_start") or 0)
            quote_counts = Counter(_tokens(evidence.get("exact_quote") or ""))
            page_chunks = [
                chunk
                for chunk in chunks
                if int((chunk.get("metadata") or {}).get("page_start") or 0) == page_number
            ]
            page_chunks.sort(
                key=lambda chunk: -sum(
                    min(Counter(_tokens(chunk.get("text") or ""))[token], count)
                    for token, count in quote_counts.items()
                )
            )
            for chunk in page_chunks[:1]:
                metadata = chunk.get("metadata") or {}
                identity = (
                    int(metadata.get("page_start") or 0),
                    int(metadata.get("chunk_index") or 0),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                selected.append(chunk)
                if len(selected) >= limit:
                    return selected
    return selected


def _balanced_chunks(chunks: list[dict], limit: int) -> list[dict]:
    """Keep basic Q&A usable when lexical retrieval has no shared language."""
    if not chunks or limit <= 0:
        return []
    by_page: dict[int, dict] = {}
    for chunk in chunks:
        page_number = int((chunk.get("metadata") or {}).get("page_start") or 0)
        by_page.setdefault(page_number, chunk)
    pages = [by_page[page] for page in sorted(by_page)]
    if len(pages) <= limit:
        return pages
    indexes = {
        round(index * (len(pages) - 1) / (limit - 1))
        for index in range(limit)
    } if limit > 1 else {0}
    return [pages[index] for index in sorted(indexes)][:limit]


def _merge_chunk_groups(groups: list[list[dict]], limit: int) -> list[dict]:
    """Round-robin retrieval signals so one backend cannot crowd out the rest."""
    selected: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    positions = [0 for _ in groups]
    while len(selected) < limit:
        advanced = False
        for group_index, group in enumerate(groups):
            while positions[group_index] < len(group):
                chunk = group[positions[group_index]]
                positions[group_index] += 1
                metadata = chunk.get("metadata") or {}
                identity = (
                    str(metadata.get("task_id") or ""),
                    int(metadata.get("page_start") or 0),
                    int(metadata.get("chunk_index") or 0),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                selected.append(chunk)
                advanced = True
                break
            if len(selected) >= limit:
                break
        if not advanced:
            break
    return selected


def _load_task(task_id: str) -> dict:
    payload = ARTIFACTS.read_result(task_id)
    if not payload or payload.get("paper_task") is not True:
        raise ValueError("论文任务不存在")
    return payload


def _task_retrieval(
    task_id: str,
    question: str,
    history: list[dict] | None = None,
    limit: int = 8,
) -> tuple[dict, list[dict], dict]:
    payload = _load_task(task_id)
    paper_chunks = _paper_chunks(task_id, payload)
    retrieval_query = _retrieval_query(question, history)
    diagnostics = {
        "strategy": "none",
        "query_rewritten": retrieval_query != re.sub(r"\s+", " ", str(question or "")).strip(),
        "matched_chunk_count": 0,
        "retrieved_pages": [],
    }

    explicit_pages = _explicit_page_numbers(question)
    if explicit_pages:
        page_chunks = [
            chunk
            for chunk in paper_chunks
            if int((chunk.get("metadata") or {}).get("page_start") or 0) in explicit_pages
        ]
        if not page_chunks:
            diagnostics["strategy"] = "requested_page_missing"
            return payload, [], diagnostics
        chunks = _rank(page_chunks, retrieval_query, limit) or page_chunks[:limit]
        diagnostics.update(
            strategy="explicit_page",
            matched_chunk_count=len(page_chunks),
            retrieved_pages=sorted(
                {int((chunk.get("metadata") or {}).get("page_start") or 0) for chunk in chunks}
            ),
        )
        return payload, chunks, diagnostics

    vector_chunks: list[dict] = []
    if vector_index_capability()[0]:
        try:
            vector_chunks = [
                chunk
                for chunk in VectorStoreManager().query(task_id, retrieval_query, n_results=limit)
                if (chunk.get("metadata") or {}).get("source_type") == "paper_page"
                and (chunk.get("distance") is None or float(chunk.get("distance")) <= 0.9)
            ]
        except Exception as exc:
            logger.warning(f"向量检索不可用，使用本地分页检索: {exc}")
    lexical_matches = _rank_matches(paper_chunks, retrieval_query)
    report_matches = _report_hint_chunks(payload, paper_chunks, retrieval_query, limit)
    diagnostics["matched_chunk_count"] = len(lexical_matches)
    chunks = _merge_chunk_groups(
        [report_matches, lexical_matches, vector_chunks],
        limit,
    )
    strategies = [
        name
        for name, values in (
            ("report_hint", report_matches),
            ("lexical", lexical_matches),
            ("vector", vector_chunks),
        )
        if values
    ]
    if strategies:
        diagnostics["strategy"] = "+".join(strategies)
    if not chunks:
        chunks = _balanced_chunks(paper_chunks, limit)
        if chunks:
            diagnostics["strategy"] = "balanced_fallback"
    diagnostics["retrieved_pages"] = sorted(
        {int((chunk.get("metadata") or {}).get("page_start") or 0) for chunk in chunks}
    )
    return payload, chunks, diagnostics


def _task_chunks(task_id: str, question: str, limit: int = 8) -> tuple[dict, list[dict]]:
    payload, chunks, _ = _task_retrieval(task_id, question, limit=limit)
    return payload, chunks


def _library_chunks(
    question: str,
    history: list[dict] | None = None,
    limit: int = 10,
) -> list[dict]:
    chunks: list[dict] = []
    for result_file in ARTIFACTS.iter_result_files() or []:
        payload = ARTIFACTS.read_result(result_file.task_id)
        if payload and payload.get("paper_task") is True:
            chunks.extend(_paper_chunks(result_file.task_id, payload))
    return _rank(chunks, _retrieval_query(question, history), limit)


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


_GROUNDING_FAILURE_DETAILS = {
    "retrieval_miss": "未检索到与当前问法匹配的原文段落；这不代表论文一定未提及，请补充完整术语、页码或换一种问法。",
    "requested_page_missing": "指定页码没有可用的分页原文，请核对 PDF 页码。",
    "response_format_invalid": "模型回答未通过结构校验，请重试。",
    "citation_missing": "模型给出了回答但没有提供可校验的原文引用，请缩小问题范围后重试。",
    "citation_rejected": "模型给出的页码或逐字引文未通过原文校验，未经证实的结论已被拒绝展示。",
    "insufficient_source": "已检索到相关原文，但当前证据仍不足以支持可靠回答。",
}


def _grounding_failure(status: str, *, retrieval: dict | None = None) -> dict:
    detail = _GROUNDING_FAILURE_DETAILS[status]
    result = {
        "answer": f"原文证据不足：{detail}",
        "sources": [],
        "grounding_status": status,
        "grounding_detail": detail,
    }
    if retrieval:
        result["retrieval_strategy"] = retrieval.get("strategy") or "none"
        result["retrieved_pages"] = retrieval.get("retrieved_pages") or []
    return result


def _ground_task_answer(
    raw: str,
    payload: dict,
    chunks: list[dict],
    retrieval: dict | None = None,
) -> dict:
    try:
        parsed = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        return _grounding_failure("response_format_invalid", retrieval=retrieval)
    if not isinstance(parsed, dict):
        return _grounding_failure("response_format_invalid", retrieval=retrieval)
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
    rejected_citation = False
    for citation in citations:
        if not isinstance(citation, dict):
            rejected_citation = True
            continue
        try:
            page_number = int(citation.get("page"))
        except (TypeError, ValueError):
            rejected_citation = True
            continue
        quote = re.sub(r"\s+", " ", str(citation.get("exact_quote") or "")).strip()
        page_text = re.sub(r"\s+", " ", pages.get(page_number, ""))
        if page_number not in allowed_pages or len(quote) < 8 or quote.casefold() not in page_text.casefold():
            rejected_citation = True
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
    if not answer:
        return _grounding_failure("response_format_invalid", retrieval=retrieval)
    if not sources:
        if citations or rejected_citation:
            return _grounding_failure("citation_rejected", retrieval=retrieval)
        if "原文证据不足" in answer:
            if (retrieval or {}).get("strategy") == "balanced_fallback" and not (retrieval or {}).get("matched_chunk_count"):
                return _grounding_failure("retrieval_miss", retrieval=retrieval)
            return _grounding_failure("insufficient_source", retrieval=retrieval)
        return _grounding_failure("citation_missing", retrieval=retrieval)
    return {
        "answer": answer,
        "sources": sources,
        "grounding_status": "source_grounded",
        "grounding_detail": "页码与逐字引文已通过原文校验。",
        "retrieval_strategy": (retrieval or {}).get("strategy") or "unknown",
        "retrieved_pages": (retrieval or {}).get("retrieved_pages") or sorted(allowed_pages),
    }


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
        chunks = _library_chunks(question, history)
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
    payload, chunks, retrieval = _task_retrieval(task_id, question, history)
    if not chunks:
        status = "requested_page_missing" if retrieval.get("strategy") == "requested_page_missing" else "retrieval_miss"
        return _grounding_failure(status, retrieval=retrieval)
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
    return _ground_task_answer(
        response.choices[0].message.content or "",
        payload,
        chunks,
        retrieval,
    )
