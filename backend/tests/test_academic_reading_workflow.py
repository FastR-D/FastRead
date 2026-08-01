import json
from types import SimpleNamespace

import fitz
import pytest

from app.repositories.note_artifacts import NoteArtifactRepository
from app.services import chat_service
from app.services.academic_evidence import assess_academic_identity, normalize_venue
from app.services.note_task_service import NoteTaskService
from app.services.paper_ingest_service import PaperIngestService
from app.services.reading_report_service import ReadingReportService
from app.services.verification import fetching, source_intel


def _pdf_bytes(*page_texts: str) -> bytes:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def test_academic_gate_requires_complete_top4_identity():
    gate = assess_academic_identity({
        "url": "https://www.usenix.org/conference/usenixsecurity25/presentation/example",
        "official_record_verified": True,
        "verified_academic_metadata": {
            "title": "A Security Paper",
            "authors": ["Alice", "Bob"],
            "published_at": "2025",
            "venue": "34th USENIX Security Symposium",
            "source_url": "https://www.usenix.org/conference/usenixsecurity25/presentation/example",
        },
    })

    assert gate["level"] == "A1"
    assert gate["gate_passed"] is True
    assert gate["venue"]["id"] == "usenix_security"
    assert normalize_venue("ACM CCS")["id"] == "acm_ccs"


def test_academic_gate_does_not_promote_preprint_to_formal_venue():
    gate = assess_academic_identity({
        "title": "A Security Paper",
        "author": "Alice",
        "published_at": "2025",
        "venue": "IEEE S&P",
        "url": "https://arxiv.org/abs/2501.00001",
    })

    assert gate["level"] == "B1"
    assert gate["gate_passed"] is False
    assert "preprint_not_formal_venue_record" in gate["warnings"]


def test_ordinary_web_article_is_not_mislabeled_as_incomplete_paper():
    gate = assess_academic_identity({
        "title": "A news report",
        "author": "Reporter",
        "published_at": "2025-01-01",
        "url": "https://news.example/story",
    })

    assert gate["level"] == "N/A"
    assert gate["has_academic_signal"] is False


def test_academic_citation_metadata_is_extracted_and_classified():
    html = """
    <html><head>
      <meta name="citation_title" content="Verified Systems Paper" />
      <meta name="citation_author" content="Alice" />
      <meta name="citation_author" content="Bob" />
      <meta name="citation_publication_date" content="2025" />
      <meta name="citation_conference_title" content="ACM CCS" />
      <meta name="citation_doi" content="10.1145/1234.5678" />
      <meta name="citation_pdf_url" content="https://dl.acm.org/paper.pdf" />
    </head><body>This is the full paper body used for classification.</body></html>
    """

    snapshot = fetching._html_snapshot("https://dl.acm.org/doi/10.1145/1234.5678", html)
    source = source_intel.classify_source({"url": snapshot["url"]}, snapshot)

    assert snapshot["authors"] == ["Alice", "Bob"]
    assert snapshot["venue"] == "ACM CCS"
    assert source["academic"]["level"] == "A1"
    assert source["academic"]["gate_passed"] is True


def test_pdf_ingest_persists_pages_and_academic_boundary(tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = PaperIngestService(repo)

    created = service.ingest_pdf(
        content=_pdf_bytes(
            "FastRead Study. We introduce a staged security analysis method.",
            "The evaluation compares three baselines and reports limitations.",
        ),
        filename="paper.pdf",
    )

    result = repo.read_result(created["task_id"])
    paper = result["paper_document"]
    assert paper["page_count"] == 2
    assert paper["pages"][0]["page"] == 1
    assert "staged security analysis" in paper["pages"][0]["text"]
    assert paper["academic_gate"]["gate_passed"] is False
    assert repo.read_status(created["task_id"])["status"] == "SUCCESS"


def test_reading_report_requires_and_persists_verified_page_quotes(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    created = PaperIngestService(repo).ingest_pdf(
        content=_pdf_bytes(
            "The paper studies phishing detection. The method uses a two-stage classifier.",
            "The main contribution is a reproducible benchmark. Evaluation uses three baselines.",
        ),
        filename="paper.pdf",
    )
    task_id = created["task_id"]
    payload = {
        "title": "FastRead report",
        "executive_summary": "This study explains the problem, method, evidence, and limits.",
        "key_questions": [
            {
                "question": "What problem is studied?",
                "answer": "Phishing detection.",
                "why_it_matters": "It is a security problem.",
                "evidence": [{"exact_quote": "The paper studies phishing detection.", "page": 1}],
                "verification_status": "source_only",
            },
            {
                "question": "What method is used?",
                "answer": "A two-stage classifier.",
                "why_it_matters": "It defines the process.",
                "evidence": [{"exact_quote": "The method uses a two-stage classifier.", "page": 1}],
                "verification_status": "source_only",
            },
            {
                "question": "What is contributed?",
                "answer": "A reproducible benchmark.",
                "why_it_matters": "It supports comparison.",
                "evidence": [{"exact_quote": "The main contribution is a reproducible benchmark.", "page": 2}],
                "verification_status": "source_only",
            },
            {
                "question": "How is it evaluated?",
                "answer": "Against three baselines.",
                "why_it_matters": "It tests the claim.",
                "evidence": [{"exact_quote": "Evaluation uses three baselines.", "page": 2}],
                "verification_status": "source_only",
            },
        ],
        "process": [{"step": "Detection", "description": "Run the two-stage classifier."}],
        "contributions": [{
            "title": "Benchmark",
            "description": "A reproducible benchmark.",
            "evidence": "The main contribution is a reproducible benchmark.",
        }],
        "limitations": ["The source does not establish field-wide consensus."],
        "terms": [{"term": "baseline", "explanation": "A comparison method."}],
        "suggested_questions": ["How are the baselines selected?"],
    }

    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
            )

    fake_gpt = SimpleNamespace(
        model="fake-model",
        client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
    )
    monkeypatch.setattr(
        "app.services.reading_report_service.GPTProvider.create",
        lambda **_kwargs: fake_gpt,
    )

    service = ReadingReportService(repo)
    report = service.generate(task_id=task_id, provider_id="p1", model_name="m1")

    assert len(report["key_questions"]) == 4
    assert report["key_questions"][0]["evidence"][0]["page_start"] == 1
    assert report["key_questions"][2]["evidence"][0]["page_start"] == 2
    assert report["key_questions"][0]["evidence"][0]["verified_in_source"] is True
    assert repo.read_result(task_id)["insights"]["reading_report"]["title"] == "FastRead report"

    summary = service.save_personal_summary(task_id=task_id, summary="我的 300 字内总结")
    assert summary["content"] == "我的 300 字内总结"
    with pytest.raises(ValueError, match="300"):
        service.save_personal_summary(task_id=task_id, summary="长" * 301)


def test_chat_chunks_include_paper_pages_with_page_metadata(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    created = PaperIngestService(repo).ingest_pdf(
        content=_pdf_bytes("This page contains a sufficiently long academic method description for retrieval."),
        filename="paper.pdf",
    )
    monkeypatch.setattr(chat_service, "ARTIFACTS", repo)

    chunks = chat_service._load_task_chunks(created["task_id"])

    paper_chunks = [chunk for chunk in chunks if chunk["metadata"]["source_type"] == "paper_page"]
    assert paper_chunks
    assert paper_chunks[0]["metadata"]["page_start"] == 1


def test_url_verification_rebuilds_claims_from_fetched_body(monkeypatch, tmp_path):
    repo = NoteArtifactRepository(tmp_path)
    service = NoteTaskService(repo)
    created = service.create_verification_task(url="https://example.org/paper.pdf", max_claims=5)
    task_id = created["task_id"]
    captured = {}

    monkeypatch.setattr(
        "app.services.note_task_service.verification_fetching.fetch_source_snapshot",
        lambda *_args, **_kwargs: {
            "url": "https://example.org/paper.pdf",
            "canonical_url": "https://example.org/paper.pdf",
            "title": "Paper",
            "text": "The paper introduces a secure protocol. The evaluation uses three datasets.",
            "page_spans": [{"page": 1, "start": 0, "end": 74}],
            "fetch_status": "pdf_ok",
            "source_type": "pdf",
        },
    )

    def fake_verify(verification, **_kwargs):
        captured["claims"] = [item["claim"] for item in verification["claims"]]
        return {**verification, "result": {"status": "insufficient", "audit": {}}}

    monkeypatch.setattr("app.services.note_task_service.verify_claims_online", fake_verify)

    service.execute_verification_task(task_id)

    assert captured["claims"]
    assert all("https://example.org" not in claim for claim in captured["claims"])
    assert any("secure protocol" in claim for claim in captured["claims"])
