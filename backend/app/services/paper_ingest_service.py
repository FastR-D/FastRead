from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from app.enmus.task_status_enums import TaskStatus
from app.repositories.note_artifacts import NoteArtifactRepository
from app.services.academic_evidence import assess_academic_identity
from app.services.verification.fetching import fetch_source_snapshot, parse_pdf_bytes


class PaperIngestService:
    def __init__(self, artifacts: NoteArtifactRepository | None = None):
        self.artifacts = artifacts or NoteArtifactRepository()

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
        title = str(
            metadata.get("title")
            or unverified_supplement.get("title")
            or self._title_from_text(text)
        ).strip()
        authors = (
            metadata.get("authors")
            or ([metadata.get("author")] if metadata.get("author") else [])
            or unverified_supplement.get("authors")
            or ([unverified_supplement.get("author")] if unverified_supplement.get("author") else [])
        )
        pages = self._pages_from_snapshot(snapshot)
        academic_gate = assess_academic_identity(metadata)
        task_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        paper_document = {
            "id": task_id,
            "title": title,
            "authors": authors,
            "venue": academic_gate.get("venue") or {},
            "year": academic_gate.get("year"),
            "doi": academic_gate.get("doi") or "",
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
            "pages": pages,
            "page_count": len(pages),
            "text_chars": len(text),
            "academic_gate": academic_gate,
            "retrieved_at": snapshot.get("retrieved_at") or created_at,
        }
        result = {
            "paper_task": True,
            "markdown": "",
            "transcript": {
                "full_text": text,
                "segments": [],
                "language": "unknown",
                "page_spans": snapshot.get("page_spans") or [],
            },
            "audio_meta": {
                "title": title,
                "platform": "paper",
                "raw_info": {
                    "url": paper_document["source_url"],
                    "authors": authors,
                    "venue": paper_document["venue"],
                    "year": paper_document["year"],
                    "doi": paper_document["doi"],
                },
            },
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
                "scores": {},
                "cards": [],
                "academic_gate": academic_gate,
            },
        }
        self.artifacts.write_result(task_id, result)
        self.artifacts.write_status(task_id, TaskStatus.SUCCESS, "论文正文与分页信息已导入")
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
        snapshot = fetch_source_snapshot(url, overrides or {})
        return self._persist(
            snapshot=snapshot,
            source_url=url,
            provider_id=provider_id,
            model_name=model_name,
            overrides=overrides,
        )
