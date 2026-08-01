import json
import os
import re
from typing import Optional

from app.core.settings import get_settings
from app.repositories.note_artifacts import NoteArtifactRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

ARTIFACTS = NoteArtifactRepository()
VECTOR_DB_DIR = get_settings().vector_db_dir


def _chunk_markdown(markdown: str) -> list[dict]:
    """按 H2/H3 标题拆分 markdown 为语义块。"""
    sections = re.split(r'(?=^#{2,3}\s)', markdown, flags=re.MULTILINE)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 30:
            continue
        heading_match = re.match(r'^(#{2,3})\s+(.+)', section)
        title = heading_match.group(2).strip() if heading_match else "intro"
        chunks.append({
            "text": section,
            "metadata": {"source_type": "markdown", "section_title": title},
        })
    return chunks


def _chunk_transcript(segments: list[dict], window_size: int = 15, overlap: int = 3) -> list[dict]:
    """将转录 segments 按滑动窗口分组。"""
    if not segments:
        return []
    chunks = []
    step = max(window_size - overlap, 1)
    for i in range(0, len(segments), step):
        window = segments[i:i + window_size]
        if not window:
            break
        text = "\n".join(
            f"[{seg.get('start', 0):.0f}s] {seg.get('text', '')}" for seg in window
        )
        chunks.append({
            "text": text,
            "metadata": {
                "source_type": "transcript",
                "start_time": window[0].get("start", 0),
                "end_time": window[-1].get("end", 0),
            },
        })
    return chunks


def _build_meta_chunk(audio_meta: dict) -> list[dict]:
    """将视频元信息（标题、作者、描述、标签等）构建为可检索的 chunk。"""
    if not audio_meta:
        return []

    raw = audio_meta.get("raw_info", {}) or {}
    parts = []

    title = audio_meta.get("title") or raw.get("title", "")
    if title:
        parts.append(f"视频标题：{title}")

    uploader = raw.get("uploader", "")
    if uploader:
        parts.append(f"视频作者/UP主：{uploader}")

    desc = raw.get("description", "")
    if desc:
        parts.append(f"视频简介：{desc[:500]}")

    tags = raw.get("tags", [])
    if tags and isinstance(tags, list):
        parts.append(f"标签：{', '.join(str(t) for t in tags[:20])}")

    duration = audio_meta.get("duration", 0)
    if duration:
        m, s = divmod(int(duration), 60)
        parts.append(f"视频时长：{m}分{s}秒")

    platform = audio_meta.get("platform", "")
    if platform:
        parts.append(f"平台：{platform}")

    url = raw.get("webpage_url", "")
    if url:
        parts.append(f"链接：{url}")

    if not parts:
        return []

    return [{
        "text": "\n".join(parts),
        "metadata": {"source_type": "meta"},
    }]


def _chunk_plain_text(text: str, size: int = 700, overlap: int = 100) -> list[str]:
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


def _chunk_paper_pages(note_data: dict) -> list[dict]:
    paper = note_data.get("paper_document") or {}
    chunks = []
    for page in paper.get("pages") or []:
        page_number = max(1, int(page.get("page") or 1))
        for text in _chunk_plain_text(page.get("text") or ""):
            chunks.append({
                "text": text,
                "metadata": {
                    "source_type": "paper_page",
                    "page_start": page_number,
                    "page_end": page_number,
                    "source_url": paper.get("pdf_url") or paper.get("source_url") or "",
                    "doi": paper.get("doi") or "",
                },
            })
    return chunks


def _chunk_json_section(value: dict | list | None, source_type: str) -> list[dict]:
    if not value:
        return []
    text = json.dumps(value, ensure_ascii=False, default=str)
    return [
        {"text": chunk, "metadata": {"source_type": source_type}}
        for chunk in _chunk_plain_text(text, size=520, overlap=80)
    ]


class VectorStoreManager:
    """基于 ChromaDB 的笔记向量存储管理器。"""

    def __init__(self):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise RuntimeError(
                "当前本地环境未安装 ChromaDB，知识库问答向量索引不可用。"
                "如需启用，请运行：backend\\.venv\\Scripts\\python.exe -m pip install chromadb"
            ) from exc

        VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(VECTOR_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

    def _collection_name(self, task_id: str) -> str:
        """ChromaDB collection 名称：直接使用 task_id（UUID 格式合法）。"""
        return task_id

    def index_task(self, task_id: str) -> None:
        """读取笔记结果并建立向量索引。"""
        note_data = ARTIFACTS.read_result(task_id)
        if not note_data:
            logger.warning(f"笔记文件不存在，跳过索引: {ARTIFACTS.result_path(task_id)}")
            return

        markdown = note_data.get("markdown", "")
        transcript = note_data.get("transcript", {})
        segments = transcript.get("segments", [])

        audio_meta = note_data.get("audio_meta", {})

        meta_chunks = _build_meta_chunk(audio_meta)
        md_chunks = _chunk_markdown(markdown)
        is_paper = bool(note_data.get("paper_task") or note_data.get("paper_document"))
        tr_chunks = [] if is_paper else _chunk_transcript(segments)
        paper_chunks = _chunk_paper_pages(note_data)
        insights = note_data.get("insights") or {}
        reading_chunks = _chunk_json_section(insights.get("reading_report"), "reading_report")
        verification_chunks = _chunk_json_section(insights.get("verification"), "verification")
        all_chunks = meta_chunks + md_chunks + tr_chunks + paper_chunks + reading_chunks + verification_chunks

        if not all_chunks:
            logger.warning(f"笔记内容为空，跳过索引: {task_id}")
            return

        col_name = self._collection_name(task_id)

        # 删除旧 collection（幂等）
        try:
            self._client.delete_collection(col_name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine"},
        )

        documents = [c["text"] for c in all_chunks]
        metadatas = [c["metadata"] for c in all_chunks]
        ids = [f"{task_id}_{i}" for i in range(len(all_chunks))]

        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"向量索引完成: task_id={task_id}, chunks={len(all_chunks)}")

    def _parse_results(self, results: dict) -> list[dict]:
        """将 ChromaDB query 结果转换为 chunk 列表。"""
        chunks = []
        if not results or not results.get("documents") or not results["documents"][0]:
            return chunks
        for i in range(len(results["documents"][0])):
            chunks.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return chunks

    def query(self, task_id: str, query_text: str, n_results: int = 6) -> list[dict]:
        """
        按固定配额从各来源检索。论文分页原文优先，报告和核验证据仅作辅助；
        普通视频任务仍保留 meta/markdown/transcript 配额。
        """
        col_name = self._collection_name(task_id)
        try:
            collection = self._client.get_collection(col_name)
        except Exception:
            logger.warning(f"Collection 不存在: {col_name}")
            return []

        all_chunks = []

        # 每种来源的配额
        quotas = {
            "paper_page": 4,
            "reading_report": 1,
            "verification": 1,
            "meta": 1,
            "markdown": 2,
            "transcript": 3,
        }

        for source_type, quota in quotas.items():
            try:
                results = collection.query(
                    query_texts=[query_text],
                    n_results=quota,
                    where={"source_type": source_type},
                )
                all_chunks.extend(self._parse_results(results))
            except Exception:
                pass

        return all_chunks

    def delete_index(self, task_id: str) -> None:
        """删除指定任务的向量索引。"""
        col_name = self._collection_name(task_id)
        try:
            self._client.delete_collection(col_name)
            logger.info(f"已删除向量索引: {task_id}")
        except Exception:
            pass

    def is_indexed(self, task_id: str) -> bool:
        """检查指定任务是否已建立完整索引（含 meta 信息）。"""
        col_name = self._collection_name(task_id)
        try:
            col = self._client.get_collection(col_name)
            if col.count() == 0:
                return False
            # 检查是否包含 meta chunk，旧索引可能缺失
            meta = col.get(where={"source_type": "meta"}, limit=1)
            return len(meta["ids"]) > 0
        except Exception:
            return False
