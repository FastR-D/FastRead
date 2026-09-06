from __future__ import annotations

import json
import re

from .store import Store


class EvidenceRepository:
    """One immutable document-version boundary for report, chat and neighbors."""

    def __init__(self, store: Store, workspace, paper_id, version_id):
        self.store, self.workspace = store, workspace
        self.paper_id, self.version_id = paper_id, version_id
        self.generated = None

    def read_result(self, task_id):
        if task_id != self.paper_id:
            raise LookupError("paper_not_found")
        paper, _, document = self.store.document(self.workspace, task_id, self.version_id)
        report = self.store.one("SELECT content FROM report_versions WHERE paper_id=? AND version_id=? ORDER BY created DESC LIMIT 1",
                                (task_id, self.version_id))
        return {"paper_task": True, "paper_document": document, "insights": {
            "reading_report": json.loads(report["content"]) if report else None,
            "personal_summary": {"content": paper["summary"]}}}

    def update_result(self, task_id, mutator):
        # Generation remains staged in memory until the worker commits under its lease.
        self.generated = mutator(self.read_result(task_id))
        return self.generated

    def chunks(self):
        self.store.document(self.workspace, self.paper_id, self.version_id)
        return self.store.all("SELECT id,page,ordinal,text FROM evidence_chunks WHERE version_id=? ORDER BY page,ordinal", (self.version_id,))

    def vector_query(self, question, limit):
        from app.services.vector_store import VectorStoreManager
        self.store.document(self.workspace, self.paper_id, self.version_id)
        manager = VectorStoreManager()
        return manager.query(self.version_id, question, n_results=limit,
                             paper_result=self.read_result(self.paper_id), chunks=self.chunks())

    def bind(self, sources):
        chunks = self.chunks()
        for source in sources:
            page = int(source.get("page_start") or source.get("page") or 0)
            quote = re.sub(r"\s+", " ", str(source.get("exact_quote") or "")).casefold()
            matches = [c["id"] for c in chunks if c["page"] == page and quote and quote in re.sub(r"\s+", " ", c["text"]).casefold()]
            source.update(document_version_id=self.version_id, chunk_ids=matches,
                          citation_status="located" if matches else "page_located",
                          support_status="not_independently_verified")
        return sources
