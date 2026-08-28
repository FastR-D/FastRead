from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from app.core.settings import get_settings
from app.db.evidence_dao import EvidenceHubDAO
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.gpt_provider import GPTProvider
from app.services.llm_compat import create_chat_completion


EVIDENCE_ROLES = {"question", "method", "experiment", "limitation", "other"}

TOPIC_CHAT_PROMPT = """你是 FastRead 的专题知识库研究助手。你只能依据下方给出的专题成员论文分页原文回答。

{context}

要求：
1. 综合多篇论文时，明确哪些结论由哪些论文报告；不要把多篇论文共同出现的陈述写成领域共识。
2. 每个实质结论都必须在句末标注一个或多个来源编号，例如 [S1] 或 [S1][S3]。
3. 只使用上面已经给出的来源编号，不要生成逐字引文、页码、链接或新的来源编号；这些由程序绑定。
4. 不使用模型记忆、常识或专题之外的论文补足答案。现有来源无法回答时，只写“专题原文证据不足”。
5. 用中文写成连贯报告或回答，避免堆砌零散 bullet。

只输出回答正文，不要 JSON、代码围栏或标题。"""

TOPIC_SYNTHESIS_PROMPT = """你只负责把程序给出的跨论文证据整理成结构化比较，不负责找证据。

输入包含专题、成员论文和若干证据记录；每条证据都有固定编号 E1、E2……。请完成三类比较：
1. common_reports：至少两篇不同论文都明确报告的共同点；
2. differences：论文在问题、方法、实验或结论上的差异；
3. conflicts：证据中可以直接确认的冲突。没有就返回空数组，禁止猜测。

同时给出 idea_feasibility：现有论文已经做到什么、关键反例和局限，以及一个可执行的最小验证实验建议。

约束：
- 只能引用输入中的 evidence_ids，不要抄写或改写逐字引文、页码、链接和论文 ID；程序会绑定并复核。
- common_reports 的每一项必须引用至少两篇论文的证据。
- 共同作者、同一会议、同一年或都属于“评测论文”不是有研究价值的共同点；common_reports 只保留问题、假设、方法、实验或结论层面的共同点。
- 每个 statement 写成信息完整的中文句子，说明具体对象和差异，禁止“与方法相关”“提供了证据”等空泛模板。
- 用户假设不视为论文结论；证据不足时放进 evidence_gaps。
- 最小验证实验必须明确对象、变量/对照和可观察结果，并表述为建议而不是论文已经证明的事实。

只输出以下 JSON 对象，不要代码围栏：
{
  "common_reports": [{"statement": "", "evidence_ids": ["E1", "E2"]}],
  "differences": [{"statement": "", "evidence_ids": ["E1", "E3"]}],
  "conflicts": [{"statement": "", "evidence_ids": ["E2", "E4"]}],
  "evidence_gaps": [""],
  "idea_feasibility": {
    "problem": "",
    "what_papers_achieved": [{"statement": "", "evidence_ids": ["E1"]}],
    "counterexamples_and_limitations": [{"statement": "", "evidence_ids": ["E2"]}],
    "minimum_validation_experiment": "",
    "evidence_to_read": [""]
  }
}"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def _chunk_page(text: str, size: int = 1200, overlap: int = 160) -> list[str]:
    page_text = str(text or "")
    if not page_text.strip():
        return []
    chunks = []
    step = size - overlap
    for start in range(0, len(page_text), step):
        chunk = page_text[start:start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(page_text):
            break
    return chunks


def _query_terms(value: str) -> set[str]:
    text = str(value or "").lower()
    words = re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    return set(words + [chinese[index:index + 2] for index in range(max(len(chinese) - 1, 0))])


def _rank_source_chunks(chunks: list[dict], query: str) -> list[dict]:
    terms = _query_terms(query)
    if not terms:
        return chunks
    scored = []
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        chunk_terms = _query_terms(text)
        overlap = len(terms & chunk_terms)
        phrase_hits = sum(1 for term in terms if term in text.lower())
        score = overlap * 3 + phrase_hits * 2
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored]


def _canonical_quote(text: str, query: str, max_words: int = 18) -> str:
    """Choose a short, relevant verbatim span; the model never copies quotes."""
    source = str(text or "")
    words = list(re.finditer(r"[A-Za-z0-9]+(?:[-'’][A-Za-z0-9]+)*|[\u4e00-\u9fff]", source))
    if not words:
        return ""
    width = min(max_words, len(words))
    query_terms = _query_terms(query)
    best = None
    for start in range(0, len(words) - width + 1):
        end = start + width - 1
        candidate = source[words[start].start():words[end].end()]
        candidate_terms = _query_terms(candidate)
        overlap = len(query_terms & candidate_terms)
        phrase_hits = sum(1 for term in query_terms if term in candidate.lower())
        score = overlap * 3 + phrase_hits * 2
        ranked = (score, -start, candidate)
        if best is None or ranked > best:
            best = ranked
    return best[2] if best else ""


def _sentence_candidates(text: str, max_chars: int = 650) -> list[str]:
    """Return exact sentence-like spans; model selection never rewrites quotes."""
    source = str(text or "")
    candidates = []
    for raw in re.split(r"(?<=[.!?。！？])\s+|[\r\n]+", source):
        span = raw.strip()
        if len(span) < 40:
            continue
        if len(span) > max_chars:
            span = span[:max_chars].rstrip()
        if span and span in source and span not in candidates:
            candidates.append(span)
    if not candidates:
        fallback = source[:max_chars].strip()
        if fallback:
            candidates.append(fallback)
    return candidates


class EvidenceHubService:
    def __init__(
        self,
        dao: EvidenceHubDAO | None = None,
        artifacts: PaperArtifactRepository | None = None,
        data_dir: Path | None = None,
    ):
        settings = get_settings()
        self.dao = dao or EvidenceHubDAO()
        self.artifacts = artifacts or PaperArtifactRepository()
        self.data_dir = Path(data_dir or settings.integration_data_dir)

    def paper_document(self, task_id: str) -> tuple[dict, dict]:
        result = self.artifacts.read_result(task_id)
        paper = (result or {}).get("paper_document") or {}
        if not result or not paper or not result.get("paper_task"):
            raise ValueError("论文任务不存在")
        if not paper.get("content_hash"):
            stable = json.dumps(
                [{"page": page.get("page"), "text": page.get("text") or ""} for page in paper.get("pages") or []],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            paper["content_hash"] = hashlib.sha256(stable).hexdigest()

            def attach_hash(latest: dict) -> dict:
                latest_paper = latest.setdefault("paper_document", {})
                latest_paper.setdefault("content_hash", paper["content_hash"])
                return latest

            result = self.artifacts.update_result(task_id, attach_hash)
            paper = result["paper_document"]
        return result, paper

    @staticmethod
    def _page(paper: dict, page_number: int) -> dict:
        page = next((item for item in paper.get("pages") or [] if int(item.get("page") or 0) == page_number), None)
        if not page:
            raise ValueError("页码不在已解析论文范围内")
        return page

    def validate_quote(
        self,
        task_id: str,
        page_number: int,
        exact_quote: str,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> tuple[dict, int, int]:
        _, paper = self.paper_document(task_id)
        page = self._page(paper, page_number)
        text = str(page.get("text") or "")
        quote = str(exact_quote or "")
        if not quote or len(quote) > 20000:
            raise ValueError("逐字引用不能为空且不能超过 20000 字符")
        offsets_supplied = start_offset is not None and end_offset is not None
        if start_offset is None or end_offset is None:
            start_offset = text.find(quote)
            if start_offset >= 0:
                end_offset = start_offset + len(quote)
            else:
                # PDF text extraction may change line wrapping while preserving
                # every lexical token. Match whitespace flexibly, then keep the
                # original page substring as the canonical verbatim citation.
                parts = [part for part in re.split(r"\s+", quote.strip()) if part]
                match = re.search(
                    r"\s+".join(re.escape(part) for part in parts),
                    text,
                    re.IGNORECASE,
                ) if parts else None
                start_offset = match.start() if match else -1
                end_offset = match.end() if match else -1
        if start_offset < 0 or end_offset <= start_offset or end_offset > len(text):
            raise ValueError("原文偏移超出页内文本范围")
        if offsets_supplied and text[start_offset:end_offset] != quote:
            raise ValueError("逐字引用与指定页码和原文偏移不匹配")
        return paper, start_offset, end_offset

    def list_annotations(self, task_id: str) -> list[dict]:
        self.paper_document(task_id)
        return self.dao.list_annotations(task_id)

    def create_annotation(self, task_id: str, payload: dict) -> dict:
        paper, start, end = self.validate_quote(
            task_id,
            int(payload["page"]),
            payload["exact_quote"],
            int(payload["start_offset"]),
            int(payload["end_offset"]),
        )
        note = str(payload.get("note") or "")
        if len(note) > 10000:
            raise ValueError("批注不能超过 10000 字符")
        return self.dao.create_annotation({
            "task_id": task_id,
            "page": int(payload["page"]),
            "start_offset": start,
            "end_offset": end,
            "exact_quote": payload["exact_quote"],
            "note": note,
            "source_hash": paper["content_hash"],
        })

    def update_annotation(self, task_id: str, annotation_id: str, payload: dict) -> dict:
        current = self.dao.get_annotation(task_id, annotation_id)
        if not current:
            raise LookupError("摘录不存在")
        merged = {**current, **{key: value for key, value in payload.items() if value is not None}}
        paper, start, end = self.validate_quote(
            task_id,
            int(merged["page"]),
            merged["exact_quote"],
            int(merged["start_offset"]),
            int(merged["end_offset"]),
        )
        note = str(merged.get("note") or "")
        if len(note) > 10000:
            raise ValueError("批注不能超过 10000 字符")
        updated = self.dao.update_annotation(task_id, annotation_id, {
            "page": int(merged["page"]),
            "start_offset": start,
            "end_offset": end,
            "exact_quote": merged["exact_quote"],
            "note": note,
            "source_hash": paper["content_hash"],
        })
        if not updated:
            raise LookupError("摘录不存在")
        return updated

    def delete_annotation(self, task_id: str, annotation_id: str) -> None:
        if not self.dao.delete_annotation(task_id, annotation_id):
            raise LookupError("摘录不存在")

    def create_topic(self, payload: dict) -> dict:
        question = str(payload.get("question") or "").strip()
        if not question:
            raise ValueError("研究问题不能为空")
        hypotheses = [str(item).strip() for item in payload.get("user_hypotheses") or [] if str(item).strip()]
        return self.dao.create_topic(question, str(payload.get("scope_statement") or "").strip(), hypotheses)

    def update_topic(self, topic_id: str, payload: dict) -> dict:
        if "question" in payload and not str(payload.get("question") or "").strip():
            raise ValueError("研究问题不能为空")
        cleaned = dict(payload)
        if "question" in cleaned:
            cleaned["question"] = str(cleaned["question"]).strip()
        if "scope_statement" in cleaned:
            cleaned["scope_statement"] = str(cleaned["scope_statement"] or "").strip()
        if "user_hypotheses" in cleaned:
            cleaned["user_hypotheses"] = [
                str(item).strip() for item in cleaned.get("user_hypotheses") or [] if str(item).strip()
            ]
        updated = self.dao.update_topic(topic_id, cleaned)
        if not updated:
            raise LookupError("专题不存在")
        return updated

    def get_topic(self, topic_id: str) -> dict:
        topic = self.dao.get_topic(topic_id)
        if not topic:
            raise LookupError("专题不存在")
        for link in topic["papers"]:
            try:
                _, paper = self.paper_document(link["task_id"])
                link["title"] = paper.get("title") or "未命名论文"
                link["content_hash"] = paper.get("content_hash") or ""
            except ValueError:
                link["title"] = "论文任务已不可用"
                link["missing"] = True
        topic["evidence_matrix"] = self._matrix(topic["evidence_items"])
        return topic

    def delete_topic(self, topic_id: str) -> None:
        records = self.dao.delete_topic(topic_id)
        if not records and not self.dao.get_topic(topic_id):
            # The DAO returns an empty list for both an empty topic and a missing one;
            # cleanup remains idempotent at the filesystem layer.
            return
        synth_root = (self.data_dir / "syntheses").resolve()
        for raw_path in records:
            path = Path(raw_path).resolve()
            if path.is_file() and synth_root in path.parents:
                path.unlink(missing_ok=True)

    def add_topic_paper(self, topic_id: str, task_id: str) -> dict:
        self.paper_document(task_id)
        link = self.dao.add_topic_paper(topic_id, task_id)
        self.refresh_topic_evidence(topic_id)
        return link

    def remove_topic_paper(self, topic_id: str, task_id: str) -> None:
        if not self.dao.remove_topic_paper(topic_id, task_id):
            raise LookupError("专题中没有这篇论文")

    @staticmethod
    def _report_pages(result: dict) -> set[int]:
        report = ((result.get("insights") or {}).get("reading_report") or {})
        pages = set()
        for question in report.get("key_questions") or []:
            for evidence in question.get("evidence") or []:
                page = evidence.get("page_start") or evidence.get("page")
                if page:
                    pages.add(int(page))
        for contribution in report.get("contributions") or []:
            evidence_items = contribution.get("evidence") or []
            if not isinstance(evidence_items, list):
                continue
            for evidence in evidence_items:
                page = evidence.get("page_start") or evidence.get("page")
                if page:
                    pages.add(int(page))
        return pages

    def _topic_chat_sources(self, topic: dict, question: str, mode: str) -> list[dict]:
        per_paper: list[list[dict]] = []
        for link in topic["papers"]:
            result, paper = self.paper_document(link["task_id"])
            title = paper.get("title") or link.get("title") or "未命名论文"
            all_chunks = []
            chunks_by_page: dict[int, list[dict]] = {}
            for page in paper.get("pages") or []:
                page_number = int(page.get("page") or 0)
                if page_number < 1:
                    continue
                page_chunks = [{
                    "task_id": link["task_id"],
                    "title": title,
                    "page": page_number,
                    "text": text,
                    "source_url": paper.get("pdf_url") or paper.get("source_url") or "",
                    "doi": paper.get("doi") or "",
                } for text in _chunk_page(page.get("text") or "")]
                chunks_by_page[page_number] = page_chunks
                all_chunks.extend(page_chunks)

            report = ((result.get("insights") or {}).get("reading_report") or {})
            report_query = " ".join([
                question,
                str(report.get("executive_summary") or ""),
                " ".join(str(item.get("question") or "") for item in report.get("key_questions") or []),
                " ".join(str(item.get("title") or "") for item in report.get("contributions") or []),
            ])
            # The user's question may be Chinese while the papers are English.
            # Blend the persisted report vocabulary into retrieval so lexical
            # mismatch cannot silently remove an entire member paper.
            ranked = _rank_source_chunks(all_chunks, report_query)
            cited_chunks = [
                chunk
                for page_number in sorted(self._report_pages(result))
                for chunk in chunks_by_page.get(page_number, [])
            ]
            if not ranked:
                ranked = cited_chunks or all_chunks[:1]
            selected = []
            seen = set()
            for chunk in ranked + cited_chunks:
                key = (chunk["page"], chunk["text"])
                if key in seen:
                    continue
                seen.add(key)
                selected.append(chunk)
                if len(selected) >= 5:
                    break
            if not selected and all_chunks:
                selected = [all_chunks[0]]
                if len(all_chunks) > 1:
                    selected.append(all_chunks[-1])
            if selected:
                per_paper.append(selected)

        sources = []
        while per_paper and len(sources) < 18:
            next_round = []
            for paper_chunks in per_paper:
                if paper_chunks:
                    sources.append(paper_chunks.pop(0))
                    if len(sources) >= 18:
                        break
                if paper_chunks:
                    next_round.append(paper_chunks)
            per_paper = next_round
        for index, source in enumerate(sources, 1):
            source["source_id"] = f"S{index}"
            source["exact_quote"] = _canonical_quote(source["text"], question)
        return [source for source in sources if source["exact_quote"]]

    def ask_topic(self, topic_id: str, payload: dict) -> dict:
        topic = self.get_topic(topic_id)
        if not topic["papers"]:
            raise ValueError("请先向专题知识库加入论文")
        mode = str(payload.get("mode") or "question")
        question = str(payload.get("question") or "").strip()
        if mode == "summary":
            question = question or (
                f"请用一段连贯中文统一总结专题“{topic['question']}”。分别概括每篇成员论文的"
                "研究问题、方法和主要贡献，再比较它们的共同点与关键差异。每篇论文至少使用一个"
                "来源编号，整段最多引用四个来源编号；只陈述这些逐字来源能够直接支持的内容。"
            )
        if not question:
            raise ValueError("问题不能为空")

        sources = self._topic_chat_sources(topic, question, mode)
        if not sources:
            raise ValueError("专题成员论文中没有可用于回答的分页原文")
        context = "\n\n".join(
            f"[{source['source_id']}] {source['title']} · 第 {source['page']} 页\n"
            f"程序已核对的可引用原句：{source['exact_quote']}\n"
            f"相邻原文：{source['text']}"
            for source in sources
        )
        messages = [{"role": "system", "content": TOPIC_CHAT_PROMPT.format(context=context)}]
        for message in list(payload.get("history") or [])[-12:]:
            role = str(message.get("role") or "")
            content = str(message.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                if role == "assistant":
                    content = re.sub(r"\[S\d+\]", "", content).strip()
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})

        gpt = GPTProvider.create(
            provider_id=str(payload.get("provider_id") or ""),
            model_name=str(payload.get("model_name") or ""),
        )
        response = create_chat_completion(
            gpt.client,
            model=gpt.model,
            messages=messages,
            temperature=0.1,
        )
        answer = str(response.choices[0].message.content or "").strip()
        if answer == "专题原文证据不足":
            return {"answer": answer, "sources": [], "grounding_status": "insufficient"}
        source_map = {source["source_id"]: source for source in sources}
        referenced_ids = set(re.findall(r"\[(S\d+)\]", answer))
        validated = []
        if not answer or not referenced_ids or not referenced_ids.issubset(source_map):
            raise ValueError("专题知识库回答使用了无效或缺失的来源编号")
        for source in sources:
            source_id = source["source_id"]
            if source_id not in referenced_ids:
                continue
            paper, start, end = self.validate_quote(
                source["task_id"],
                source["page"],
                source["exact_quote"],
            )
            page = self._page(paper, source["page"])
            canonical_quote = str(page.get("text") or "")[start:end]
            validated.append({
                "source_id": source_id,
                "task_id": source["task_id"],
                "title": source["title"],
                "page_start": source["page"],
                "page_end": source["page"],
                "exact_quote": canonical_quote,
                "text": canonical_quote[:500],
                "source_type": "paper_page",
                "source_url": source["source_url"],
                "doi": source["doi"],
            })
        if mode == "summary" and len(topic["papers"]) >= 2:
            cited_papers = {item["task_id"] for item in validated}
            if len(cited_papers) < 2:
                raise ValueError("专题统一总结必须引用至少两篇成员论文的原文")
        return {"answer": answer, "sources": validated, "grounding_status": "source_grounded"}

    def add_evidence(self, topic_id: str, payload: dict) -> dict:
        topic = self.get_topic(topic_id)
        task_id = str(payload.get("task_id") or "")
        if task_id not in {item["task_id"] for item in topic["papers"]}:
            raise ValueError("证据论文尚未加入专题")
        page_number = int(payload.get("page") or 0)
        quote = str(payload.get("exact_quote") or "")
        paper, start, end = self.validate_quote(task_id, page_number, quote)
        canonical_quote = str(self._page(paper, page_number).get("text") or "")[start:end]
        role = str(payload.get("role") or "other")
        if role not in EVIDENCE_ROLES:
            raise ValueError("未知证据角色")
        return self.dao.add_evidence({
            "topic_id": topic_id,
            "task_id": task_id,
            "page": page_number,
            "exact_quote": canonical_quote,
            "user_note": str(payload.get("user_note") or "")[:10000],
            "role": role,
            "source_kind": "manual",
            "source_ref": "",
        })

    def refresh_topic_evidence(self, topic_id: str) -> list[dict]:
        topic = self.dao.get_topic(topic_id)
        if not topic:
            raise LookupError("专题不存在")
        existing_refs = {item["source_ref"] for item in topic["evidence_items"] if item.get("source_ref")}
        for link in topic["papers"]:
            task_id = link["task_id"]
            try:
                result, _ = self.paper_document(task_id)
            except ValueError:
                continue
            for annotation in self.dao.list_annotations(task_id):
                ref = f"annotation:{annotation['id']}"
                if ref in existing_refs:
                    continue
                self.dao.add_evidence({
                    "topic_id": topic_id,
                    "task_id": task_id,
                    "page": annotation["page"],
                    "exact_quote": annotation["exact_quote"],
                    "user_note": annotation["note"],
                    "role": "other",
                    "source_kind": "annotation",
                    "source_ref": ref,
                })
                existing_refs.add(ref)
            report = ((result.get("insights") or {}).get("reading_report") or {})
            evidence_groups = []
            for index, question in enumerate(report.get("key_questions") or []):
                evidence_groups.append(("question", f"question:{index}", question.get("evidence") or []))
            for index, contribution in enumerate(report.get("contributions") or []):
                raw = contribution.get("evidence") or []
                evidence_groups.append(("method", f"contribution:{index}", raw if isinstance(raw, list) else []))
            for index, process in enumerate(report.get("process") or []):
                raw = process.get("evidence") or []
                evidence_groups.append(("experiment", f"process:{index}", raw if isinstance(raw, list) else []))
            for role, prefix, evidences in evidence_groups:
                for index, evidence in enumerate(evidences):
                    page_number = int(evidence.get("page_start") or evidence.get("page") or 0)
                    quote = str(evidence.get("exact_quote") or "")
                    ref = f"report:{task_id}:{prefix}:{index}"
                    if ref in existing_refs or not quote or page_number < 1:
                        continue
                    try:
                        self.validate_quote(task_id, page_number, quote)
                    except ValueError:
                        continue
                    self.dao.add_evidence({
                        "topic_id": topic_id,
                        "task_id": task_id,
                        "page": page_number,
                        "exact_quote": quote,
                        "user_note": "",
                        "role": role,
                        "source_kind": "report",
                        "source_ref": ref,
                    })
                    existing_refs.add(ref)
        return self.get_topic(topic_id)["evidence_items"]

    def delete_evidence(self, topic_id: str, evidence_id: str) -> None:
        if not self.dao.delete_evidence(topic_id, evidence_id):
            raise LookupError("专题证据不存在")

    @staticmethod
    def _matrix(items: list[dict]) -> dict:
        matrix = {role: [] for role in ("question", "method", "experiment", "limitation", "other")}
        for item in items:
            matrix.setdefault(item.get("role") or "other", []).append(item)
        return matrix

    def _validated_citations(self, topic: dict, citations: list[dict]) -> list[dict]:
        allowed_tasks = {item["task_id"] for item in topic["papers"]}
        valid = []
        seen = set()
        for citation in citations or []:
            task_id = str(citation.get("task_id") or "")
            page = int(citation.get("page") or 0)
            quote = str(citation.get("exact_quote") or "")
            key = (task_id, page, quote)
            if task_id not in allowed_tasks or key in seen:
                continue
            try:
                self.validate_quote(task_id, page, quote)
            except ValueError:
                continue
            seen.add(key)
            valid.append({"task_id": task_id, "page": page, "exact_quote": quote})
        return valid

    def create_synthesis(self, topic_id: str, payload: dict) -> dict:
        self.refresh_topic_evidence(topic_id)
        topic = self.get_topic(topic_id)
        proposed = payload.get("proposed") if isinstance(payload.get("proposed"), dict) else None
        provider_id = str(payload.get("provider_id") or "").strip()
        model_name = str(payload.get("model_name") or "").strip()
        if not proposed and provider_id and model_name:
            proposed = self._generate_synthesis_proposal(topic, provider_id, model_name)
        kind = "model" if proposed else "manual"
        if proposed:
            synthesis = self._sanitize_proposed(topic, proposed)
        else:
            synthesis = self._manual_synthesis(topic)
        synthesis.update({
            "version": 1,
            "topic_id": topic_id,
            "generated_at": utc_now(),
            "kind": kind,
            "user_hypotheses": topic["user_hypotheses"],
        })
        if kind == "model":
            synthesis["model"] = {"provider_id": provider_id, "model_name": model_name}
        synthesis_id = hashlib.sha256(
            json.dumps(synthesis, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]
        path = self.data_dir / "syntheses" / topic_id / f"{synthesis_id}.json"
        atomic_write_json(path, synthesis)
        record = self.dao.create_synthesis_record(topic_id, str(path), kind)
        synthesis["id"] = record["id"]
        return synthesis

    def _generate_synthesis_proposal(self, topic: dict, provider_id: str, model_name: str) -> dict:
        if len(topic.get("papers") or []) < 2:
            raise ValueError("跨论文综合至少需要两篇成员论文")
        titles = {paper["task_id"]: paper.get("title") or paper["task_id"] for paper in topic["papers"]}
        evidence_map: dict[str, dict] = {}
        evidence_payload = []
        seen = set()

        def add_candidate(*, task_id: str, page: int, exact_quote: str, context: str, role: str) -> None:
            key = (task_id, page, exact_quote)
            if not task_id or page < 1 or not exact_quote or key in seen:
                return
            seen.add(key)
            evidence_id = f"E{len(evidence_payload) + 1}"
            evidence_map[evidence_id] = {
                "task_id": task_id,
                "page": page,
                "exact_quote": exact_quote,
            }
            evidence_payload.append({
                "evidence_id": evidence_id,
                "paper": titles.get(task_id, task_id),
                "role": role,
                "page": page,
                "verbatim_evidence": context[:1600],
            })

        for item in (topic.get("evidence_items") or [])[:80]:
            add_candidate(
                task_id=item["task_id"],
                page=int(item["page"]),
                exact_quote=str(item["exact_quote"]),
                context=str(item["exact_quote"]),
                role=str(item.get("role") or "other"),
            )

        retrieval_query = " ".join([
            str(topic.get("question") or ""),
            str(topic.get("scope_statement") or ""),
            " ".join(str(item) for item in topic.get("user_hypotheses") or []),
        ])
        for source in self._topic_chat_sources(topic, retrieval_query, "summary"):
            for quote in _sentence_candidates(str(source["text"])):
                add_candidate(
                    task_id=str(source["task_id"]),
                    page=int(source["page"]),
                    exact_quote=quote,
                    context=quote,
                    role="related_page_context",
                )
                if len(evidence_payload) >= 120:
                    break
            if len(evidence_payload) >= 120:
                break
        if not evidence_payload:
            raise ValueError("专题暂无经过页码和逐字引文校验的证据，无法生成跨论文综合")

        gpt = GPTProvider.create(provider_id=provider_id, model_name=model_name)
        response = create_chat_completion(
            gpt.client,
            model=gpt.model,
            messages=[
                {"role": "system", "content": TOPIC_SYNTHESIS_PROMPT},
                {"role": "user", "content": json.dumps({
                    "question": topic["question"],
                    "scope_statement": topic.get("scope_statement") or "",
                    "user_hypotheses": topic.get("user_hypotheses") or [],
                    "papers": [{"task_id": item["task_id"], "title": titles[item["task_id"]]} for item in topic["papers"]],
                    "evidence": evidence_payload,
                }, ensure_ascii=False)},
            ],
            temperature=0.1,
        )
        raw = str(response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE).strip()
        try:
            proposal = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"跨论文综合模型输出不是有效 JSON: {exc}") from exc
        if not isinstance(proposal, dict):
            raise ValueError("跨论文综合模型输出必须是 JSON 对象")

        def bind_claims(value: object) -> list[dict]:
            bound = []
            for claim in (value if isinstance(value, list) else []):
                if not isinstance(claim, dict):
                    continue
                citations = []
                for evidence_id in dict.fromkeys(str(item) for item in claim.get("evidence_ids") or []):
                    if evidence_id in evidence_map:
                        citations.append(evidence_map[evidence_id])
                statement = str(claim.get("statement") or "").strip()
                if statement and citations:
                    bound.append({"statement": statement, "citations": citations})
            return bound

        normalized = {
            "common_reports": bind_claims(proposal.get("common_reports")),
            "differences": bind_claims(proposal.get("differences")),
            "conflicts": bind_claims(proposal.get("conflicts")),
            "evidence_gaps": [str(item).strip() for item in proposal.get("evidence_gaps") or [] if str(item).strip()],
        }
        feasibility = proposal.get("idea_feasibility") if isinstance(proposal.get("idea_feasibility"), dict) else {}
        normalized["idea_feasibility"] = {
            "problem": str(feasibility.get("problem") or topic["question"]).strip(),
            "what_papers_achieved": bind_claims(feasibility.get("what_papers_achieved")),
            "counterexamples_and_limitations": bind_claims(feasibility.get("counterexamples_and_limitations")),
            "minimum_validation_experiment": str(feasibility.get("minimum_validation_experiment") or "").strip(),
            "evidence_to_read": [
                str(item).strip()
                for item in feasibility.get("evidence_to_read") or []
                if str(item).strip() and not re.fullmatch(r"E\d+", str(item).strip(), flags=re.IGNORECASE)
            ],
        }
        if not normalized["idea_feasibility"]["evidence_to_read"]:
            normalized["idea_feasibility"]["evidence_to_read"] = normalized["evidence_gaps"]
        return normalized

    def _manual_synthesis(self, topic: dict) -> dict:
        items = topic["evidence_items"]
        matrix = self._matrix(items)
        common_reports = []
        differences = []
        gaps = []
        for role, role_items in matrix.items():
            tasks = {item["task_id"] for item in role_items}
            citations = [
                {"task_id": item["task_id"], "page": item["page"], "exact_quote": item["exact_quote"]}
                for item in role_items
            ]
            if len(tasks) >= 2:
                common_reports.append({
                    "statement": f"多篇论文共同报告了与“{role}”相关的原文证据；这里只表示跨论文共同出现，不代表领域共识。",
                    "citations": citations,
                })
            elif role_items:
                differences.extend({
                    "statement": f"该论文在“{role}”维度提供了独立证据，尚无第二篇论文形成共同报告。",
                    "citations": [citation],
                } for citation in citations)
            else:
                gaps.append(f"“{role}”维度暂无逐字页码证据。")
        return {
            "question": topic["question"],
            "scope_statement": topic["scope_statement"],
            "common_reports": common_reports,
            "differences": differences,
            "conflicts": [],
            "evidence_gaps": gaps,
            "idea_feasibility": {
                "problem": topic["question"],
                "what_papers_achieved": differences + common_reports,
                "unsupported_hypotheses": topic["user_hypotheses"],
                "counterexamples_and_limitations": matrix.get("limitation") or [],
                "minimum_validation_experiment": "尚未由现有逐字证据确定；请基于证据矩阵手工填写最小验证实验。",
                "evidence_to_read": gaps,
            },
            "evidence_matrix": matrix,
        }

    def _sanitize_proposed(self, topic: dict, proposed: dict) -> dict:
        sanitized: dict = {
            "question": topic["question"],
            "scope_statement": topic["scope_statement"],
            "common_reports": [],
            "differences": [],
            "conflicts": [],
            "evidence_gaps": [str(item) for item in proposed.get("evidence_gaps") or []],
            "idea_feasibility": proposed.get("idea_feasibility") or {},
            "evidence_matrix": self._matrix(topic["evidence_items"]),
        }
        for section in ("common_reports", "differences", "conflicts"):
            for claim in proposed.get(section) or []:
                citations = self._validated_citations(topic, claim.get("citations") or [])
                if not citations:
                    continue
                if section == "common_reports" and len({item["task_id"] for item in citations}) < 2:
                    sanitized["evidence_gaps"].append(
                        f"共同报告候选“{claim.get('statement') or ''}”不足两篇论文逐字证据，已删除。"
                    )
                    continue
                statement = str(claim.get("statement") or "").replace("领域共识", "多篇论文共同报告")
                sanitized[section].append({"statement": statement, "citations": citations})
        feasibility = sanitized["idea_feasibility"]
        if not isinstance(feasibility, dict):
            feasibility = {}
        def sanitize_feasibility_claims(value: object) -> list[dict]:
            claims = []
            for claim in (value if isinstance(value, list) else []):
                if not isinstance(claim, dict):
                    continue
                statement = str(claim.get("statement") or "").strip()
                citations = self._validated_citations(topic, claim.get("citations") or [])
                if statement and citations:
                    claims.append({"statement": statement, "citations": citations})
            return claims

        sanitized["idea_feasibility"] = {
            "problem": str(feasibility.get("problem") or topic["question"]),
            "what_papers_achieved": sanitize_feasibility_claims(feasibility.get("what_papers_achieved")),
            "unsupported_hypotheses": topic["user_hypotheses"],
            "counterexamples_and_limitations": sanitize_feasibility_claims(feasibility.get("counterexamples_and_limitations")),
            "minimum_validation_experiment": str(feasibility.get("minimum_validation_experiment") or ""),
            "evidence_to_read": [str(item) for item in feasibility.get("evidence_to_read") or sanitized["evidence_gaps"]],
        }
        return sanitized

    def list_syntheses(self, topic_id: str) -> list[dict]:
        self.get_topic(topic_id)
        synth_root = (self.data_dir / "syntheses").resolve()
        results = []
        for record in self.dao.list_synthesis_records(topic_id):
            path = Path(record["artifact_path"]).resolve()
            if synth_root not in path.parents or not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            payload["id"] = record["id"]
            results.append(payload)
        return results
