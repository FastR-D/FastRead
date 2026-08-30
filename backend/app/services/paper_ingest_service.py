from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid
from urllib.parse import urljoin

from app.enmus.task_status_enums import TaskStatus
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.db.paper_task_dao import upsert_paper_task
from app.services.academic_identity_service import AcademicIdentityService
from app.services.academic_identity_resolver import resolve_document_claim_record
from app.services.paper_fetching import fetch_source_snapshot, parse_pdf_bytes
from app.services.metadata_normalization import normalize_paper_metadata
from app.utils.logger import get_logger


logger = get_logger(__name__)


class PaperIngestService:
    def __init__(
        self,
        artifacts: PaperArtifactRepository | None = None,
        academic_resolver=None,
    ):
        self.artifacts = artifacts or PaperArtifactRepository()
        self._academic_resolver = academic_resolver or resolve_document_claim_record
        self._identity = AcademicIdentityService()

    @staticmethod
    def _pages_from_snapshot(snapshot: dict) -> list[dict]:
        text = snapshot.get("text") or ""
        pages = []
        for span in snapshot.get("page_spans") or []:
            start = max(0, int(span.get("start") or 0))
            end = min(len(text), int(span.get("end") or 0))
            page = max(1, int(span.get("page") or len(pages) + 1))
            page_text = text[start:end].strip()
            if page_text:
                pages.append({"page": page, "text": page_text, "start": start, "end": end})
        if not pages and text:
            pages.append({"page": 1, "text": text, "start": 0, "end": len(text)})
        return pages

    @staticmethod
    def _title_from_text(text: str) -> str:
        for line in (text or "").splitlines():
            candidate = re.sub(r"\s+", " ", line).strip()
            if 8 <= len(candidate) <= 240:
                return candidate
        return "未命名论文"

    def _persist(
        self,
        *,
        snapshot: dict,
        source_url: str = "",
        filename: str = "",
        provider_id: str = "",
        model_name: str = "",
        overrides: dict | None = None,
    ) -> dict:
        overrides = overrides or {}
        unverified_supplement = {
            key: value
            for key, value in overrides.items()
            if value not in (None, "", [])
        }
        text = (snapshot.get("text") or "").strip()
        if snapshot.get("fetch_status") not in {"ok", "pdf_ok"} or not text:
            raise ValueError("论文原文无法解析；扫描版、加密 PDF 或抓取失败时不能生成报告")

        metadata = {
            **snapshot,
            "document_type": "paper",
            "url": snapshot.get("url") or source_url or "",
            "canonical_url": snapshot.get("canonical_url") or snapshot.get("url") or source_url or "",
            "unverified_supplement": unverified_supplement,
        }
        pages = self._pages_from_snapshot(snapshot)
        metadata_contract = normalize_paper_metadata(
            metadata,
            first_page_text=str((pages[0] if pages else {}).get("text") or ""),
            unverified_supplement=unverified_supplement,
            resolved_identity={
                key: metadata.get(key)
                for key in (
                    "official_record_verified", "registry_record_verified", "registry_name",
                    "registry_record_url", "registry_retrieved_at", "verified_academic_metadata",
                )
                if metadata.get(key) not in (None, "", {}, [])
            },
        )
        normalized = metadata_contract["normalized_metadata"]
        verified_identity = metadata_contract["verified_identity"]
        title = str(normalized.get("title") or self._title_from_text(text)).strip()
        authors = normalized.get("authors") or []
        academic_gate = verified_identity["academic_gate"]
        task_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        paper_document = {
            "id": task_id,
            "title": title,
            "authors": authors,
            "venue": academic_gate.get("venue") or {},
            "year": normalized.get("year"),
            "doi": normalized.get("doi") or "",
            "source_url": source_url or snapshot.get("url") or "",
            "resolved_source_url": snapshot.get("url") or source_url or "",
            "pdf_url": metadata.get("pdf_url") or (source_url if snapshot.get("source_type") == "pdf" else ""),
            "filename": filename,
            "content_hash": metadata.get("content_hash") or "",
            "source_bytes": metadata.get("source_bytes") or 0,
            "source_status": metadata.get("source_status") or "blocked",
            "parser": metadata.get("parser") or "",
            "parser_version": metadata.get("parser_version") or "",
            "page_count_total": metadata.get("page_count_total") or len(pages),
            "page_count_parsed": metadata.get("page_count_parsed") or len(pages),
            "text_truncated": bool(metadata.get("text_truncated")),
            "extraction_limits": metadata.get("extraction_limits") or {},
            "unverified_supplement": unverified_supplement,
            "document_claimed_metadata": metadata.get("document_claimed_metadata") or {},
            "pages": pages,
            "page_count": len(pages),
            "text_chars": len(text),
            "academic_gate": academic_gate,
            "raw_metadata": metadata_contract["raw_metadata"],
            "normalized_metadata": normalized,
            "verified_identity": verified_identity,
            "metadata_contract": {
                key: metadata_contract[key]
                for key in (
                    "schema_version", "parser_version", "strategy_version", "execution_status",
                    "fallback_reasons", "normalized_at", "candidate_boundaries",
                )
            },
            "retrieved_at": snapshot.get("retrieved_at") or created_at,
        }
        result = {
            "paper_task": True,
            "paper_input": {
                "source_url": paper_document["source_url"],
                "filename": filename,
                "provider_id": provider_id,
                "model_name": model_name,
                "unverified_supplement": unverified_supplement,
            },
            "paper_document": paper_document,
            "insights": {
                "version": 1,
                "academic_gate": academic_gate,
            },
        }
        self.artifacts.write_result(task_id, result)
        self.artifacts.write_status(task_id, TaskStatus.SUCCESS, "论文正文与分页信息已导入")
        upsert_paper_task(
            {
                "task_id": task_id,
                "title": title,
                "authors": authors,
                "year": paper_document["year"],
                "venue": paper_document["venue"],
                "identity_status": academic_gate["identity_status"],
                "doi": paper_document["doi"],
                "source_url": paper_document["source_url"],
                "resolved_source_url": paper_document["resolved_source_url"],
                "pdf_url": paper_document["pdf_url"],
                "filename": filename,
                "content_hash": paper_document["content_hash"],
                "raw_metadata": metadata_contract["raw_metadata"],
                "normalized_metadata": normalized,
                "verified_identity": verified_identity,
                "metadata_schema_version": metadata_contract["schema_version"],
                "metadata_parser_version": metadata_contract["parser_version"],
                "metadata_strategy_version": metadata_contract["strategy_version"],
                "metadata_execution_status": metadata_contract["execution_status"],
                "metadata_fallback_reasons": metadata_contract["fallback_reasons"],
            }
        )
        return {"task_id": task_id, "result": result}

    def ingest_pdf(
        self,
        *,
        content: bytes,
        filename: str,
        source_url: str = "",
        provider_id: str = "",
        model_name: str = "",
        overrides: dict | None = None,
    ) -> dict:
        if not content:
            raise ValueError("PDF 文件为空")
        snapshot = parse_pdf_bytes(content, source_url)
        document_claim = snapshot.get("document_claimed_metadata") or {}
        if document_claim:
            try:
                spans = snapshot.get("page_spans") or []
                first_page = ""
                if spans:
                    first = spans[0]
                    first_page = str(snapshot.get("text") or "")[
                        int(first.get("start") or 0) : int(first.get("end") or 0)
                    ]
                preliminary = normalize_paper_metadata(snapshot, first_page_text=first_page)
                normalized = preliminary["normalized_metadata"]
                resolver_claim = {
                    **document_claim,
                    "title": normalized.get("title") or document_claim.get("title"),
                    "authors": normalized.get("authors") or document_claim.get("authors") or [],
                    "year": normalized.get("year") or document_claim.get("year"),
                }
                resolved = self._academic_resolver(resolver_claim) or {}
                if resolved:
                    snapshot = {**snapshot, **resolved}
            except Exception as exc:
                logger.warning(f"论文官方身份索引匹配失败（保留文档声明信息）: {exc}")
        return self._persist(
            snapshot=snapshot,
            source_url=source_url,
            filename=filename,
            provider_id=provider_id,
            model_name=model_name,
            overrides=overrides,
        )

    def ingest_url(
        self,
        *,
        url: str,
        provider_id: str = "",
        model_name: str = "",
        overrides: dict | None = None,
    ) -> dict:
        landing_snapshot = fetch_source_snapshot(url, overrides or {})
        snapshot = landing_snapshot
        linked_pdf_url = urljoin(
            str(landing_snapshot.get("url") or url),
            str(landing_snapshot.get("pdf_url") or "").strip(),
        )
        if (
            landing_snapshot.get("fetch_status") == "ok"
            and linked_pdf_url
            and linked_pdf_url != landing_snapshot.get("url")
        ):
            pdf_snapshot = fetch_source_snapshot(linked_pdf_url, overrides or {})
            if pdf_snapshot.get("fetch_status") == "pdf_ok" and pdf_snapshot.get("text"):
                snapshot = {
                    **pdf_snapshot,
                    "title": landing_snapshot.get("title") or pdf_snapshot.get("title"),
                    "authors": landing_snapshot.get("authors") or pdf_snapshot.get("authors") or [],
                    "author": landing_snapshot.get("author") or pdf_snapshot.get("author") or "",
                    "published_at": (
                        landing_snapshot.get("published_at")
                        or pdf_snapshot.get("published_at")
                        or ""
                    ),
                    "venue": landing_snapshot.get("venue") or pdf_snapshot.get("venue") or "",
                    "doi": landing_snapshot.get("doi") or pdf_snapshot.get("doi") or "",
                    "canonical_url": (
                        landing_snapshot.get("canonical_url")
                        or landing_snapshot.get("url")
                        or url
                    ),
                    "pdf_url": linked_pdf_url,
                    "landing_url": landing_snapshot.get("url") or url,
                    "official_record_verified": bool(
                        landing_snapshot.get("official_record_verified")
                    ),
                    "verified_academic_metadata": (
                        landing_snapshot.get("verified_academic_metadata") or {}
                    ),
                }
        return self._persist(
            snapshot=snapshot,
            source_url=url,
            provider_id=provider_id,
            model_name=model_name,
            overrides=overrides,
        )
