from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter

from app.db.paper_index_dao import (
    create_index_job,
    finish_index_job,
    latest_index_job,
    list_keyword_records,
    save_keyword_records,
)
from app.db.paper_task_dao import list_paper_tasks
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.gpt_provider import GPTProvider
from app.services.llm_compat import create_chat_completion
from app.services.paper_search_service import PaperSearchService, extract_keywords, utc_now_iso
from app.utils.logger import get_logger


logger = get_logger(__name__)

PROMPT_VERSION = "paper-abstract-keywords-v1"
STRATEGY_VERSION = "offline-ai-index-v1"
SYSTEM_PROMPT = """你是 FastRead 的离线论文索引器。只分析给定的论文标题和摘要，提取适合学术检索的关键词。
规则：
1. 输出一个 JSON 对象，结构为 {"keywords": ["keyword"]}。
2. 返回 6 到 16 个简洁、可检索、去重的英文关键词或短语。
3. 不补写摘要中不存在的论文结论、作者、会议或实验数字。
4. 不输出 Markdown 或额外解释。"""


def _strip_code_fence(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _clean_keywords(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        keyword = re.sub(r"\s+", " ", str(item or "").strip().lower())[:80]
        if len(keyword) < 2 or keyword in seen:
            continue
        seen.add(keyword)
        result.append(keyword)
        if len(result) == 20:
            break
    return result


def _abstract_from_document(document: dict) -> tuple[str, str]:
    direct = re.sub(r"\s+", " ", str(document.get("abstract") or "")).strip()
    if direct:
        return direct[:8000], "paper_document.abstract"
    pages = document.get("pages") or []
    opening = "\n".join(str(page.get("text") or "") for page in pages[:3])
    match = re.search(
        r"\babstract\b\s*[:.—-]?\s*(.{40,8000}?)(?=\s+(?:1\.?\s+)?(?:introduction|keywords?|index terms?)\b)",
        opening,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip(), "opening_pages.abstract_section"
    return "", "abstract_not_found"


class PaperIndexService:
    """Run model-assisted indexing offline, never inside click-to-search."""

    def __init__(
        self,
        search_service: PaperSearchService | None = None,
        artifacts: PaperArtifactRepository | None = None,
        model_factory=None,
        completion_factory=None,
        task_list_factory=None,
    ):
        self.search_service = search_service or PaperSearchService()
        self.artifacts = artifacts or PaperArtifactRepository()
        self._model_factory = model_factory or GPTProvider.create
        self._completion_factory = completion_factory or create_chat_completion
        self._task_list_factory = task_list_factory or list_paper_tasks

    def _corpus(self) -> list[dict]:
        tasks = list(self._task_list_factory())
        # Imported papers are the authoritative, replayable corpus for a full
        # rebuild. Previously fetched metadata leads are intentionally dropped;
        # they may enter the index again only through a later explicit refresh.
        corpus: dict[str, dict] = {}
        for task in tasks:
            task_id = str(task.get("task_id") or "")
            result = self.artifacts.read_result(task_id) or {}
            document = result.get("paper_document") or {}
            if not document:
                continue
            abstract, abstract_source = _abstract_from_document(document)
            gate = document.get("academic_gate") or {}
            venue = gate.get("venue") or {}
            paper = {
                "id": task_id,
                "task_id": task_id,
                "title": document.get("title") or task.get("title") or "未命名论文",
                "abstract": abstract,
                "abstract_source": abstract_source,
                "authors": document.get("authors") or task.get("authors") or [],
                "year": document.get("year") or task.get("year"),
                "doi": document.get("doi") or task.get("doi") or "",
                "source_url": document.get("source_url") or "",
                "pdf_url": document.get("pdf_url") or document.get("source_url") or "",
                "source": "imported_paper",
                "scope_tier": "core" if gate.get("gate_passed") else "local",
                "scope_label": "已导入全文",
                "track": gate.get("venue_track") or venue.get("track") or "",
                "venue": venue,
                "venue_id": venue.get("id") or "",
                "venue_confirmed": bool(gate.get("gate_passed")),
                "evidence_status": "full_text_imported",
                "full_text_verified": True,
                "provenance": {
                    "provider": "fastread_import",
                    "retrieved_at": utc_now_iso(),
                    "metadata_only": False,
                    "task_id": task_id,
                    "abstract_source": abstract_source,
                },
            }
            corpus[task_id] = paper
        if not corpus:
            corpus = {
                str(paper_id): dict(paper)
                for paper_id, paper in self.search_service.index.documents.items()
                if str(paper_id or "").strip()
            }
        return sorted(corpus.values(), key=lambda paper: str(paper.get("id") or ""))

    def _ai_keywords(self, *, title: str, abstract: str, provider_id: str, model_name: str) -> list[str]:
        model = self._model_factory(
            provider_id=provider_id,
            model_name=model_name,
            required=True,
        )
        response = self._completion_factory(
            model.client,
            model=model.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({"title": title, "abstract": abstract}, ensure_ascii=False),
                },
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        payload = json.loads(_strip_code_fence(response.choices[0].message.content or ""))
        return _clean_keywords(payload.get("keywords") if isinstance(payload, dict) else None)

    def rebuild(self, *, provider_id: str = "", model_name: str = "", use_ai: bool = True) -> dict:
        job_id = uuid.uuid4().hex
        provider_id = str(provider_id or "").strip()
        model_name = str(model_name or "").strip()
        create_index_job(
            job_id=job_id,
            provider_id=provider_id,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            strategy_version=STRATEGY_VERSION,
        )
        try:
            self.search_service._refresh_connection_config()
            corpus = self._corpus()
            if not corpus:
                raise ValueError("没有可重建的论文索引语料")

            records: list[dict] = []
            fallback_reasons: Counter[str] = Counter()
            ai_keyword_count = 0
            enriched: list[dict] = []
            for paper in corpus:
                abstract = str(paper.get("abstract") or "").strip()
                fallback_reason = ""
                execution_status = "ai_succeeded"
                keywords: list[str] = []
                if not use_ai:
                    fallback_reason = "ai_disabled_by_request"
                elif not provider_id or not model_name:
                    fallback_reason = "model_not_configured"
                elif not abstract:
                    fallback_reason = "abstract_missing"
                else:
                    try:
                        keywords = self._ai_keywords(
                            title=str(paper.get("title") or ""),
                            abstract=abstract,
                            provider_id=provider_id,
                            model_name=model_name,
                        )
                        if not keywords:
                            fallback_reason = "model_returned_no_keywords"
                    except Exception as exc:
                        fallback_reason = f"model_error:{type(exc).__name__}:{str(exc)[:240]}"
                        logger.warning(f"离线关键词模型失败 paper_id={paper.get('id')}: {exc}")

                if fallback_reason:
                    execution_status = "deterministic_fallback"
                    fallback_reasons[fallback_reason] += 1
                    keywords = extract_keywords(
                        str(paper.get("title") or ""),
                        abstract,
                        limit=16,
                    )
                else:
                    ai_keyword_count += 1

                indexed = {
                    **paper,
                    "keywords": keywords,
                    "keyword_strategy": "ai_abstract_keywords" if not fallback_reason else "deterministic_fallback",
                    "keyword_status": execution_status,
                    "keyword_model": model_name if not fallback_reason else "",
                    "keyword_provider_id": provider_id if not fallback_reason else "",
                    "keyword_prompt_version": PROMPT_VERSION,
                    "keyword_strategy_version": STRATEGY_VERSION,
                    "keyword_fallback_reason": fallback_reason,
                }
                enriched.append(indexed)
                records.append(
                    {
                        "paper_id": str(paper.get("id") or ""),
                        "task_id": str(paper.get("task_id") or ""),
                        "title": str(paper.get("title") or ""),
                        "abstract_hash": hashlib.sha256(abstract.encode("utf-8")).hexdigest(),
                        "keywords": keywords,
                        "execution_status": execution_status,
                        "fallback_reason": fallback_reason,
                        "provider_id": provider_id if not fallback_reason else "",
                        "model_name": model_name if not fallback_reason else "",
                        "prompt_version": PROMPT_VERSION,
                        "strategy_version": STRATEGY_VERSION,
                    }
                )

            fallback_count = len(records) - ai_keyword_count
            keyword_status = "ai_complete" if fallback_count == 0 else "completed_with_fallback"
            index_metadata = {
                "keyword_extraction": {
                    "mode": "offline_ai" if ai_keyword_count else "deterministic_fallback",
                    "ai_configured": bool(provider_id and model_name),
                    "job_id": job_id,
                    "prompt_version": PROMPT_VERSION,
                    "strategy_version": STRATEGY_VERSION,
                    "status": keyword_status,
                    "model_name": model_name,
                    "provider_id": provider_id,
                }
            }
            local_count = self.search_service.index.replace_all(enriched, metadata=index_metadata)
            save_keyword_records(job_id, records)

            es_count = 0
            search_backend = "local_inverted_index"
            error = ""
            es_health = self.search_service.elasticsearch.health()
            if es_health.get("available"):
                try:
                    es_count = self.search_service.elasticsearch.rebuild(enriched)
                    search_backend = "elasticsearch"
                except Exception as exc:
                    error = f"elasticsearch_rebuild_failed:{type(exc).__name__}:{str(exc)[:300]}"
            else:
                error = f"elasticsearch_unavailable:{es_health.get('error') or es_health.get('reason') or 'unknown'}"

            status = "completed"
            if fallback_count or search_backend != "elasticsearch":
                status = "completed_with_fallback"
            return finish_index_job(
                job_id,
                status=status,
                corpus_count=len(enriched),
                ai_keyword_count=ai_keyword_count,
                fallback_count=fallback_count,
                fallback_reasons=dict(fallback_reasons),
                local_index_count=local_count,
                elasticsearch_index_count=es_count,
                search_backend=search_backend,
                error=error,
            )
        except Exception as exc:
            finish_index_job(job_id, status="failed", error=f"{type(exc).__name__}:{str(exc)[:500]}")
            raise

    @staticmethod
    def latest_status(*, include_records: bool = False) -> dict | None:
        job = latest_index_job()
        if job and include_records:
            job["records"] = list_keyword_records(job["job_id"])
        return job
