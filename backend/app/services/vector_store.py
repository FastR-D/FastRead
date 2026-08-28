from __future__ import annotations

import re

from app.core.settings import get_settings
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.utils.logger import get_logger


logger = get_logger(__name__)
ARTIFACTS = PaperArtifactRepository()
VECTOR_DB_DIR = get_settings().vector_db_dir


def _chunk_plain_text(text: str, size: int = 700, overlap: int = 100) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    chunks = []
    step = max(size - overlap, 1)
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start : start + size].strip()
        if len(chunk) >= 30:
            chunks.append(chunk)
        if start + size >= len(cleaned):
            break
    return chunks


def _chunk_paper_pages(paper_result: dict) -> list[dict]:
    paper = paper_result.get("paper_document") or {}
    task_id = str(paper.get("id") or "")
    title = str(paper.get("title") or "")
    chunks = []
    for page in paper.get("pages") or []:
        page_number = max(1, int(page.get("page") or 1))
        for index, text in enumerate(_chunk_plain_text(page.get("text") or "")):
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
                        "source_url": paper.get("pdf_url") or paper.get("source_url") or "",
                        "doi": paper.get("doi") or "",
                    },
                }
            )
    return chunks


class VectorStoreManager:
    """ChromaDB index containing only source-grounded paper page chunks."""

    def __init__(self):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise RuntimeError(
                "当前本地环境未安装 ChromaDB，论文分页向量索引不可用。"
                "如需启用，请运行：backend\\.venv\\Scripts\\python.exe -m pip install chromadb"
            ) from exc

        VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(VECTOR_DB_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

    @staticmethod
    def _collection_name(task_id: str) -> str:
        return task_id

    def index_task(self, task_id: str) -> None:
        paper_result = ARTIFACTS.read_result(task_id)
        if not paper_result or paper_result.get("paper_task") is not True:
            logger.warning(f"论文任务不存在，跳过索引: {task_id}")
            return
        chunks = _chunk_paper_pages(paper_result)
        if not chunks:
            logger.warning(f"论文分页原文为空，跳过索引: {task_id}")
            return

        collection_name = self._collection_name(task_id)
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass
        collection = self._client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        collection.add(
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[chunk["metadata"] for chunk in chunks],
            ids=[f"{task_id}_{index}" for index in range(len(chunks))],
        )
        logger.info(f"论文分页向量索引完成: task_id={task_id}, chunks={len(chunks)}")

    @staticmethod
    def _parse_results(results: dict) -> list[dict]:
        chunks = []
        if not results or not results.get("documents") or not results["documents"][0]:
            return chunks
        for index, document in enumerate(results["documents"][0]):
            chunks.append(
                {
                    "text": document,
                    "metadata": results["metadatas"][0][index] if results.get("metadatas") else {},
                    "distance": results["distances"][0][index] if results.get("distances") else None,
                }
            )
        return chunks

    def query(self, task_id: str, query_text: str, n_results: int = 6) -> list[dict]:
        try:
            collection = self._client.get_collection(self._collection_name(task_id))
            results = collection.query(
                query_texts=[query_text],
                n_results=max(1, n_results),
                where={"source_type": "paper_page"},
            )
            return self._parse_results(results)
        except Exception as exc:
            logger.warning(f"论文分页向量检索不可用: task_id={task_id}, error={exc}")
            return []

    def delete_index(self, task_id: str) -> None:
        try:
            self._client.delete_collection(self._collection_name(task_id))
            logger.info(f"已删除论文向量索引: {task_id}")
        except Exception:
            pass

    def is_indexed(self, task_id: str) -> bool:
        try:
            collection = self._client.get_collection(self._collection_name(task_id))
            page_chunks = collection.get(where={"source_type": "paper_page"}, limit=1)
            return bool(page_chunks.get("ids"))
        except Exception:
            return False
