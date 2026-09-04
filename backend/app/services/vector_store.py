from __future__ import annotations

import importlib.util
import os
import re
from functools import lru_cache
from pathlib import Path

from app.core.settings import get_settings
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.utils.logger import get_logger


logger = get_logger(__name__)
ARTIFACTS = PaperArtifactRepository()
VECTOR_DB_DIR = get_settings().vector_db_dir
INDEX_VERSION = "paper-pages-v3-700-100"
FASTEMBED_VERSION = "0.8.0"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBEDDING_REPOSITORY = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
DEFAULT_EMBEDDING_REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
DEFAULT_EMBEDDING_DIMENSION = 384
_PINNED_MODEL_FILES = (
    "config.json",
    "model_optimized.onnx",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


def vector_index_capability() -> tuple[bool, str]:
    """Enable indexing automatically when its declared dependency is present."""
    setting = os.getenv("CHAT_VECTOR_INDEX_ENABLED", "auto").strip().lower()
    if setting in {"0", "false", "no", "off", "disabled"}:
        return False, "当前部署已关闭向量索引（CHAT_VECTOR_INDEX_ENABLED=0）"
    if importlib.util.find_spec("chromadb") is None:
        return False, "当前环境未安装 ChromaDB；基础检索仍可使用"
    if importlib.util.find_spec("fastembed") is None:
        return False, "当前环境未安装 FastEmbed 多语言嵌入组件；基础检索仍可使用"
    return True, ""


def embedding_model_config() -> dict:
    model_name = os.getenv("CHAT_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
    revision_default = DEFAULT_EMBEDDING_REVISION if model_name == DEFAULT_EMBEDDING_MODEL else ""
    repository_default = DEFAULT_EMBEDDING_REPOSITORY if model_name == DEFAULT_EMBEDDING_MODEL else ""
    return {
        "model_name": model_name,
        "repository": os.getenv("CHAT_EMBEDDING_REPOSITORY", repository_default).strip(),
        "revision": os.getenv("CHAT_EMBEDDING_MODEL_REVISION", revision_default).strip(),
        "model_dir": os.getenv("CHAT_EMBEDDING_MODEL_DIR", "").strip(),
        "cache_dir": str(get_settings().embedding_model_cache_dir),
        "threads": max(1, int(os.getenv("CHAT_EMBEDDING_THREADS", "4"))),
    }


def embedding_index_identity(config: dict | None = None) -> str:
    config = config or embedding_model_config()
    revision = config.get("revision") or "fastembed-registry"
    return f"{config['model_name']}@{revision}:fastembed-{FASTEMBED_VERSION}:mean-pooling-v1"


def _pinned_model_path(config: dict) -> str | None:
    explicit_path = config.get("model_dir") or ""
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.is_dir():
            raise RuntimeError(f"多语言嵌入模型目录不存在: {path}")
        return str(path)

    repository = config.get("repository") or ""
    revision = config.get("revision") or ""
    if not repository or not revision:
        return None

    from huggingface_hub import snapshot_download

    kwargs = {
        "repo_id": repository,
        "revision": revision,
        "cache_dir": config["cache_dir"],
        "allow_patterns": list(_PINNED_MODEL_FILES),
    }
    try:
        return snapshot_download(**kwargs, local_files_only=True)
    except Exception:
        return snapshot_download(**kwargs)


@lru_cache(maxsize=4)
def _embedding_model(
    model_name: str,
    repository: str,
    revision: str,
    model_dir: str,
    cache_dir: str,
    threads: int,
):
    from fastembed import TextEmbedding

    config = {
        "model_name": model_name,
        "repository": repository,
        "revision": revision,
        "model_dir": model_dir,
        "cache_dir": cache_dir,
        "threads": threads,
    }
    specific_model_path = _pinned_model_path(config)
    kwargs = {"specific_model_path": specific_model_path} if specific_model_path else {}
    return TextEmbedding(
        model_name=model_name,
        cache_dir=cache_dir,
        threads=threads,
        **kwargs,
    )


def _get_embedding_model(config: dict | None = None):
    config = config or embedding_model_config()
    return _embedding_model(
        config["model_name"],
        config["repository"],
        config["revision"],
        config["model_dir"],
        config["cache_dir"],
        config["threads"],
    )


def _normalize_embedding(vector) -> list[float]:
    import numpy as np

    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if not norm:
        raise RuntimeError("多语言嵌入模型返回了零向量")
    return (array / norm).tolist()


def _embed_documents(documents: list[str], config: dict | None = None) -> list[list[float]]:
    model = _get_embedding_model(config)
    return [_normalize_embedding(vector) for vector in model.passage_embed(documents, batch_size=64)]


def _embed_query(query: str, config: dict | None = None) -> list[float]:
    model = _get_embedding_model(config)
    return _normalize_embedding(next(iter(model.query_embed([query]))))


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

    def index_task(self, task_id: str) -> dict:
        paper_result = ARTIFACTS.read_result(task_id)
        if not paper_result or paper_result.get("paper_task") is not True:
            logger.warning(f"论文任务不存在，跳过索引: {task_id}")
            return {"status": "skipped", "reason": "paper_not_found", "chunk_count": 0}
        chunks = _chunk_paper_pages(paper_result)
        if not chunks:
            logger.warning(f"论文分页原文为空，跳过索引: {task_id}")
            return {"status": "skipped", "reason": "empty_pages", "chunk_count": 0}

        collection_name = self._collection_name(task_id)
        content_hash = str((paper_result.get("paper_document") or {}).get("content_hash") or "")
        embedding_config = embedding_model_config()
        embedding_identity = embedding_index_identity(embedding_config)
        try:
            existing = self._client.get_collection(collection_name)
            metadata = existing.metadata or {}
            if (
                content_hash
                and metadata.get("content_hash") == content_hash
                and metadata.get("index_version") == INDEX_VERSION
                and metadata.get("embedding_identity") == embedding_identity
                and existing.count() == len(chunks)
            ):
                logger.info(f"论文分页向量索引已是最新: task_id={task_id}, chunks={len(chunks)}")
                return {"status": "reused", "reason": "unchanged", "chunk_count": len(chunks)}
        except Exception:
            pass
        embeddings = _embed_documents([chunk["text"] for chunk in chunks], embedding_config)
        if len(embeddings) != len(chunks):
            raise RuntimeError("多语言嵌入结果数量与论文分块数量不一致")
        if (
            embedding_config["model_name"] == DEFAULT_EMBEDDING_MODEL
            and any(len(vector) != DEFAULT_EMBEDDING_DIMENSION for vector in embeddings)
        ):
            raise RuntimeError("多语言嵌入模型返回了意外的向量维度")
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass
        collection = self._client.create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",
                "content_hash": content_hash,
                "index_version": INDEX_VERSION,
                "embedding_identity": embedding_identity,
                "embedding_model": embedding_config["model_name"],
                "embedding_revision": embedding_config["revision"] or "fastembed-registry",
                "embedding_dimension": len(embeddings[0]),
            },
        )
        collection.add(
            documents=[chunk["text"] for chunk in chunks],
            embeddings=embeddings,
            metadatas=[chunk["metadata"] for chunk in chunks],
            ids=[f"{task_id}_{index}" for index in range(len(chunks))],
        )
        logger.info(f"论文分页向量索引完成: task_id={task_id}, chunks={len(chunks)}")
        return {"status": "indexed", "reason": "rebuilt", "chunk_count": len(chunks)}

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
            if not self.is_indexed(task_id):
                return []
            collection = self._client.get_collection(self._collection_name(task_id))
            query_embedding = _embed_query(query_text)
            results = collection.query(
                query_embeddings=[query_embedding],
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
            paper_result = ARTIFACTS.read_result(task_id)
            paper = (paper_result or {}).get("paper_document") or {}
            chunks = _chunk_paper_pages(paper_result or {})
            content_hash = str(paper.get("content_hash") or "")
            embedding_identity = embedding_index_identity()
            if not paper_result or not content_hash or not chunks:
                return False
            collection = self._client.get_collection(self._collection_name(task_id))
            metadata = collection.metadata or {}
            return bool(
                metadata.get("content_hash") == content_hash
                and metadata.get("index_version") == INDEX_VERSION
                and metadata.get("embedding_identity") == embedding_identity
                and collection.count() == len(chunks)
            )
        except Exception:
            return False
