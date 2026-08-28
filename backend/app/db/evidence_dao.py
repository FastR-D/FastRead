from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid

from sqlalchemy import or_

from app.db.engine import SessionLocal
from app.db.models.evidence_hub import (
    FastWriteHandoff,
    PaperAnnotation,
    PaperCandidate,
    ResearchTopic,
    ResearchTopicPaper,
    TopicEvidenceItem,
    TopicSynthesisRecord,
)


def _json(value, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _iso(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value or "")


def annotation_dict(item: PaperAnnotation) -> dict:
    return {
        "id": item.id,
        "task_id": item.task_id,
        "page": item.page,
        "start_offset": item.start_offset,
        "end_offset": item.end_offset,
        "exact_quote": item.exact_quote,
        "note": item.note or "",
        "source_hash": item.source_hash,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def candidate_dict(item: PaperCandidate) -> dict:
    raw = _json(item.raw_json, {})
    categories = raw.get("categories") or raw.get("category") or []
    if isinstance(categories, str):
        categories = [categories]
    return {
        "id": item.id,
        "title": item.title,
        "authors": _json(item.authors_json, []),
        "year": item.year,
        "venue": item.venue or "",
        "abstract": item.abstract or "",
        "doi": item.doi or "",
        "arxiv_id": item.arxiv_id or "",
        "detail_url": item.detail_url or "",
        "canonical_url": item.canonical_url or "",
        "pdf_url": item.pdf_url or "",
        "pdf_sha256": item.pdf_sha256 or "",
        "producer": item.producer,
        "upstream_id": item.upstream_id or "",
        "source_commit": item.source_commit or "",
        "fetched_at": item.fetched_at or "",
        "warnings": _json(item.warnings_json, []),
        "categories": [str(value) for value in categories if str(value)],
        "match_score": item.match_score,
        "import_status": item.import_status,
        "task_id": item.task_id,
        "discovery_status": "发现线索",
        "source_lock_status": "原文已锁定" if item.task_id else "原文未锁定",
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def topic_dict(item: ResearchTopic) -> dict:
    return {
        "id": item.id,
        "question": item.question,
        "scope_statement": item.scope_statement or "",
        "user_hypotheses": _json(item.user_hypotheses_json, []),
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def evidence_dict(item: TopicEvidenceItem) -> dict:
    return {
        "id": item.id,
        "topic_id": item.topic_id,
        "task_id": item.task_id,
        "page": item.page,
        "exact_quote": item.exact_quote,
        "user_note": item.user_note or "",
        "role": item.role,
        "source_kind": item.source_kind,
        "source_ref": item.source_ref or "",
        "created_at": _iso(item.created_at),
    }


def handoff_dict(item: FastWriteHandoff) -> dict:
    return {
        "id": item.id,
        "bundle_id": item.bundle_id,
        "project_id": item.project_id,
        "status": item.status,
        "target_path": item.target_path,
        "files": _json(item.files_json, []),
        "successful_files": _json(item.successful_files_json, []),
        "error": item.error or "",
        "manifest_hash": item.manifest_hash or "",
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


class EvidenceHubDAO:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def list_annotations(self, task_id: str) -> list[dict]:
        with self.session_factory() as db:
            rows = (
                db.query(PaperAnnotation)
                .filter(PaperAnnotation.task_id == task_id)
                .order_by(PaperAnnotation.page, PaperAnnotation.start_offset, PaperAnnotation.created_at)
                .all()
            )
            return [annotation_dict(row) for row in rows]

    def get_annotation(self, task_id: str, annotation_id: str) -> dict | None:
        with self.session_factory() as db:
            row = db.query(PaperAnnotation).filter_by(id=annotation_id, task_id=task_id).first()
            return annotation_dict(row) if row else None

    def create_annotation(self, payload: dict) -> dict:
        with self.session_factory() as db:
            row = PaperAnnotation(id=str(uuid.uuid4()), **payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            return annotation_dict(row)

    def update_annotation(self, task_id: str, annotation_id: str, payload: dict) -> dict | None:
        with self.session_factory() as db:
            row = db.query(PaperAnnotation).filter_by(id=annotation_id, task_id=task_id).first()
            if not row:
                return None
            for key, value in payload.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return annotation_dict(row)

    def delete_annotation(self, task_id: str, annotation_id: str) -> bool:
        with self.session_factory() as db:
            row = db.query(PaperAnnotation).filter_by(id=annotation_id, task_id=task_id).first()
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True

    def find_candidate_duplicate(self, normalized: dict) -> dict | None:
        checks = (
            ("doi_norm", normalized.get("doi_norm")),
            ("arxiv_norm", normalized.get("arxiv_norm")),
            ("canonical_url_norm", normalized.get("canonical_url_norm")),
            ("pdf_sha256", normalized.get("pdf_sha256")),
        )
        with self.session_factory() as db:
            for field, value in checks:
                if not value:
                    continue
                row = db.query(PaperCandidate).filter(getattr(PaperCandidate, field) == value).first()
                if row:
                    return candidate_dict(row)
        return None

    def create_candidate(self, payload: dict) -> dict:
        with self.session_factory() as db:
            row = PaperCandidate(id=str(uuid.uuid4()), **payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            return candidate_dict(row)

    def list_candidates(self, filters: dict | None = None) -> list[dict]:
        filters = filters or {}
        with self.session_factory() as db:
            query = db.query(PaperCandidate)
            if filters.get("producer"):
                query = query.filter(PaperCandidate.producer == filters["producer"])
            if filters.get("venue"):
                query = query.filter(PaperCandidate.venue.ilike(f"%{filters['venue']}%"))
            if filters.get("year") is not None:
                query = query.filter(PaperCandidate.year == filters["year"])
            if filters.get("status"):
                query = query.filter(PaperCandidate.import_status == filters["status"])
            if filters.get("category"):
                needle = f"%{filters['category']}%"
                query = query.filter(or_(PaperCandidate.warnings_json.ilike(needle), PaperCandidate.raw_json.ilike(needle)))
            rows = query.order_by(PaperCandidate.created_at.desc()).all()
            return [candidate_dict(row) for row in rows]

    def get_candidate(self, candidate_id: str) -> dict | None:
        with self.session_factory() as db:
            row = db.query(PaperCandidate).filter_by(id=candidate_id).first()
            return candidate_dict(row) if row else None

    def mark_candidate_imported(self, candidate_id: str, task_id: str, pdf_sha256: str = "") -> dict:
        with self.session_factory() as db:
            row = db.query(PaperCandidate).filter_by(id=candidate_id).first()
            if not row:
                raise ValueError("候选不存在")
            row.import_status = "imported"
            row.task_id = task_id
            if pdf_sha256:
                row.pdf_sha256 = pdf_sha256
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return candidate_dict(row)

    def delete_candidate(self, candidate_id: str) -> bool:
        with self.session_factory() as db:
            row = db.query(PaperCandidate).filter_by(id=candidate_id).first()
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True

    def create_topic(self, question: str, scope_statement: str, user_hypotheses: list[str]) -> dict:
        with self.session_factory() as db:
            row = ResearchTopic(
                id=str(uuid.uuid4()),
                question=question,
                scope_statement=scope_statement,
                user_hypotheses_json=json.dumps(user_hypotheses, ensure_ascii=False),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return topic_dict(row)

    def list_topics(self) -> list[dict]:
        with self.session_factory() as db:
            rows = db.query(ResearchTopic).order_by(ResearchTopic.updated_at.desc()).all()
            results = []
            for row in rows:
                item = topic_dict(row)
                item["paper_count"] = db.query(ResearchTopicPaper).filter_by(topic_id=row.id).count()
                item["evidence_count"] = db.query(TopicEvidenceItem).filter_by(topic_id=row.id).count()
                results.append(item)
            return results

    def get_topic(self, topic_id: str) -> dict | None:
        with self.session_factory() as db:
            row = db.query(ResearchTopic).filter_by(id=topic_id).first()
            if not row:
                return None
            result = topic_dict(row)
            result["papers"] = [
                {"task_id": link.task_id, "added_at": _iso(link.added_at)}
                for link in db.query(ResearchTopicPaper).filter_by(topic_id=topic_id).order_by(ResearchTopicPaper.added_at).all()
            ]
            result["evidence_items"] = [
                evidence_dict(item)
                for item in db.query(TopicEvidenceItem).filter_by(topic_id=topic_id).order_by(TopicEvidenceItem.role, TopicEvidenceItem.created_at).all()
            ]
            return result

    def update_topic(self, topic_id: str, payload: dict) -> dict | None:
        with self.session_factory() as db:
            row = db.query(ResearchTopic).filter_by(id=topic_id).first()
            if not row:
                return None
            if "question" in payload:
                row.question = payload["question"]
            if "scope_statement" in payload:
                row.scope_statement = payload["scope_statement"]
            if "user_hypotheses" in payload:
                row.user_hypotheses_json = json.dumps(payload["user_hypotheses"], ensure_ascii=False)
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return topic_dict(row)

    def delete_topic(self, topic_id: str) -> list[str]:
        with self.session_factory() as db:
            row = db.query(ResearchTopic).filter_by(id=topic_id).first()
            if not row:
                return []
            artifacts = [
                item.artifact_path
                for item in db.query(TopicSynthesisRecord).filter_by(topic_id=topic_id).all()
            ]
            db.query(ResearchTopicPaper).filter_by(topic_id=topic_id).delete()
            db.query(TopicEvidenceItem).filter_by(topic_id=topic_id).delete()
            db.query(TopicSynthesisRecord).filter_by(topic_id=topic_id).delete()
            db.delete(row)
            db.commit()
            return artifacts

    def add_topic_paper(self, topic_id: str, task_id: str) -> dict:
        with self.session_factory() as db:
            if not db.query(ResearchTopic).filter_by(id=topic_id).first():
                raise ValueError("专题不存在")
            row = db.query(ResearchTopicPaper).filter_by(topic_id=topic_id, task_id=task_id).first()
            if not row:
                row = ResearchTopicPaper(topic_id=topic_id, task_id=task_id)
                db.add(row)
                db.commit()
                db.refresh(row)
            return {"topic_id": topic_id, "task_id": task_id, "added_at": _iso(row.added_at)}

    def remove_topic_paper(self, topic_id: str, task_id: str) -> bool:
        with self.session_factory() as db:
            count = db.query(ResearchTopicPaper).filter_by(topic_id=topic_id, task_id=task_id).delete()
            db.query(TopicEvidenceItem).filter_by(topic_id=topic_id, task_id=task_id).delete()
            db.commit()
            return bool(count)

    def add_evidence(self, payload: dict) -> dict:
        with self.session_factory() as db:
            row = TopicEvidenceItem(id=str(uuid.uuid4()), **payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            return evidence_dict(row)

    def delete_evidence(self, topic_id: str, evidence_id: str) -> bool:
        with self.session_factory() as db:
            row = db.query(TopicEvidenceItem).filter_by(id=evidence_id, topic_id=topic_id).first()
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True

    def create_synthesis_record(self, topic_id: str, artifact_path: str, kind: str) -> dict:
        with self.session_factory() as db:
            row = TopicSynthesisRecord(
                id=str(uuid.uuid4()), topic_id=topic_id, artifact_path=artifact_path, kind=kind
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return {
                "id": row.id,
                "topic_id": row.topic_id,
                "artifact_path": row.artifact_path,
                "kind": row.kind,
                "created_at": _iso(row.created_at),
            }

    def list_synthesis_records(self, topic_id: str) -> list[dict]:
        with self.session_factory() as db:
            rows = db.query(TopicSynthesisRecord).filter_by(topic_id=topic_id).order_by(TopicSynthesisRecord.created_at.desc()).all()
            return [{
                "id": row.id,
                "topic_id": row.topic_id,
                "artifact_path": row.artifact_path,
                "kind": row.kind,
                "created_at": _iso(row.created_at),
            } for row in rows]

    def get_handoff_by_bundle_project(self, bundle_id: str, project_id: str) -> dict | None:
        with self.session_factory() as db:
            row = db.query(FastWriteHandoff).filter_by(bundle_id=bundle_id, project_id=project_id).first()
            return handoff_dict(row) if row else None

    def get_handoff(self, handoff_id: str) -> dict | None:
        with self.session_factory() as db:
            row = db.query(FastWriteHandoff).filter_by(id=handoff_id).first()
            return handoff_dict(row) if row else None

    def create_handoff(self, payload: dict) -> dict:
        with self.session_factory() as db:
            row = FastWriteHandoff(id=str(uuid.uuid4()), **payload)
            db.add(row)
            db.commit()
            db.refresh(row)
            return handoff_dict(row)

    def update_handoff(self, handoff_id: str, **changes) -> dict:
        with self.session_factory() as db:
            row = db.query(FastWriteHandoff).filter_by(id=handoff_id).first()
            if not row:
                raise ValueError("交接记录不存在")
            for key, value in changes.items():
                if key in {"files", "successful_files"}:
                    setattr(row, f"{key}_json", json.dumps(value, ensure_ascii=False))
                else:
                    setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return handoff_dict(row)

    def list_handoffs(self) -> list[dict]:
        with self.session_factory() as db:
            rows = db.query(FastWriteHandoff).order_by(FastWriteHandoff.created_at.desc()).all()
            return [handoff_dict(row) for row in rows]

    def cleanup_task_relations(self, task_id: str) -> None:
        with self.session_factory() as db:
            db.query(PaperAnnotation).filter_by(task_id=task_id).delete()
            db.query(ResearchTopicPaper).filter_by(task_id=task_id).delete()
            db.query(TopicEvidenceItem).filter_by(task_id=task_id).delete()
            candidates = db.query(PaperCandidate).filter_by(task_id=task_id).all()
            for candidate in candidates:
                candidate.task_id = None
                candidate.import_status = "pending"
            db.commit()
