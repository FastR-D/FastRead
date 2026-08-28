from contextlib import asynccontextmanager
import uuid

from fastapi.testclient import TestClient

from app import create_app
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.routers import note
from app.services.reading_report_service import PERSONAL_SUMMARY_MAX_CHARS, ReadingReportService


@asynccontextmanager
async def _lifespan(_app):
    yield


def test_summary_api_accepts_long_notes_and_markdown_export_preserves_sources(monkeypatch, tmp_path):
    task_id = str(uuid.uuid4())
    repo = PaperArtifactRepository(tmp_path)
    repo.write_result(task_id, {
        "paper_task": True,
        "paper_document": {"title": "Grounded paper", "pages": [{"page": 2, "text": "Exact source sentence."}]},
        "insights": {
            "reading_report": {
                "title": "Grounded report",
                "executive_summary": "A deterministic overview.",
                "key_questions": [{
                    "question": "What is supported?",
                    "answer": "The recorded claim.",
                    "why_it_matters": "It is traceable.",
                    "evidence": [{
                        "exact_quote": "Exact source sentence.",
                        "page_start": 2,
                        "page_end": 2,
                        "source_url": "/uploads/paper.pdf",
                        "verified_in_source": True,
                    }],
                }],
                "process": [],
                "contributions": [],
                "limitations": ["Single-paper evidence only."],
                "terms": [],
                "suggested_questions": [],
            },
        },
    })
    monkeypatch.setattr(note, "READING_REPORTS", ReadingReportService(repo))

    with TestClient(create_app(lifespan=_lifespan)) as client:
        summary_text = "长总结。" * 100
        saved = client.put(
            f"/api/reading_reports/{task_id}/personal_summary",
            json={"summary": summary_text},
        )
        exported = client.get(f"/api/reading_reports/{task_id}/export.md")

    assert saved.status_code == 200
    assert saved.json()["data"]["personal_summary"] == {
        "content": summary_text,
        "updated_at": saved.json()["data"]["personal_summary"]["updated_at"],
        "max_chars": PERSONAL_SUMMARY_MAX_CHARS,
    }
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in exported.headers["content-disposition"]
    assert "## 我的总结" in exported.text
    assert summary_text in exported.text
    assert "> “Exact source sentence.”" in exported.text
    assert "> — 第 2 页 · [来源回跳](http://testserver/uploads/paper.pdf#page=2)" in exported.text
