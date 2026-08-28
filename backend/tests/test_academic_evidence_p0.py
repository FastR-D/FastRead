import json
import socket
import threading
from types import SimpleNamespace

import fitz

from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services.academic_evidence import assess_academic_identity
from app.services import paper_fetching as fetching
from app.services.paper_ingest_service import PaperIngestService
from app.services.reading_report_service import ReadingReportService, _normalize_report


def _public_dns(monkeypatch):
    monkeypatch.setattr(
        fetching.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )


class _Response:
    def __init__(self, *, url, status_code=200, headers=None, chunks=()):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = "utf-8"
        self._chunks = list(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_bytes(self):
        yield from self._chunks


class _StreamClient:
    responses = {}

    def __init__(self, *_args, **kwargs):
        assert kwargs.get("follow_redirects") is False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def stream(self, _method, url):
        return self.responses[url]


def test_safe_fetch_rejects_loopback_without_request():
    snapshot = fetching.fetch_source_snapshot(
        "http://127.0.0.1/private",
        client_factory=_StreamClient,
    )

    assert snapshot["fetch_status"] == "failed"
    assert snapshot["source_status"] == "blocked"
    assert "non-public" in snapshot["error"]


def test_safe_fetch_rejects_hostname_resolving_private(monkeypatch):
    monkeypatch.setattr(
        fetching.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 443))
        ],
    )

    snapshot = fetching.fetch_source_snapshot(
        "https://paper.example/source",
        client_factory=_StreamClient,
    )

    assert snapshot["fetch_status"] == "failed"
    assert "non-public" in snapshot["error"]


def test_safe_fetch_validates_redirect_target(monkeypatch):
    _public_dns(monkeypatch)

    class RedirectClient(_StreamClient):
        responses = {
            "https://paper.example/start": _Response(
                url="https://paper.example/start",
                status_code=302,
                headers={"location": "http://169.254.169.254/latest/meta-data"},
            ),
        }

    snapshot = fetching.fetch_source_snapshot(
        "https://paper.example/start",
        client_factory=RedirectClient,
    )

    assert snapshot["fetch_status"] == "failed"
    assert "metadata" in snapshot["error"]


def test_safe_fetch_stream_limit_fails_closed(monkeypatch):
    _public_dns(monkeypatch)

    class LargeClient(_StreamClient):
        responses = {
            "https://paper.example/large": _Response(
                url="https://paper.example/large",
                headers={"content-type": "text/html"},
                chunks=(b"1234", b"5678"),
            ),
        }

    snapshot = fetching.fetch_source_snapshot(
        "https://paper.example/large",
        client_factory=LargeClient,
        max_bytes=6,
    )

    assert snapshot["fetch_status"] == "failed"
    assert "exceeds 6 bytes" in snapshot["error"]


def test_snapshot_extraction_limits_are_explicitly_partial():
    html_snapshot = fetching._html_snapshot(
        "https://paper.example/long",
        f"<html><body>{'x' * (fetching.TEXT_CHAR_LIMIT + 1)}</body></html>",
    )
    document = fitz.open()
    for index in range(fetching.PDF_PAGE_LIMIT + 1):
        page = document.new_page()
        if index == 0:
            page.insert_text((72, 72), "Parsed first page.")
    pdf_bytes = document.tobytes()
    document.close()
    pdf_snapshot = fetching.parse_pdf_bytes(pdf_bytes, "https://paper.example/long.pdf")

    assert html_snapshot["text_truncated"] is True
    assert html_snapshot["source_status"] == "parsed_partial"
    assert pdf_snapshot["page_count_total"] == fetching.PDF_PAGE_LIMIT + 1
    assert pdf_snapshot["page_count_parsed"] == fetching.PDF_PAGE_LIMIT
    assert pdf_snapshot["text_truncated"] is True
    assert pdf_snapshot["source_status"] == "parsed_partial"


def test_fake_doi_and_user_metadata_cannot_pass_academic_gate():
    gate = assess_academic_identity({
        "title": "Fake",
        "authors": ["Mallory"],
        "year": 2025,
        "venue": "ACM CCS",
        "doi": "10.1234/not-real",
        "url": "https://evil.example/p.pdf",
    })

    assert gate["level"] == "U"
    assert gate["gate_passed"] is False
    assert gate["official_record"] is False
    assert gate["publication_status"] == "unknown"


def test_official_domain_without_fetched_provenance_still_fails_closed():
    gate = assess_academic_identity({
        "title": "Unfetched Claim",
        "authors": ["Mallory"],
        "year": 2025,
        "venue": "USENIX Security",
        "url": "https://www.usenix.org/conference/usenixsecurity25/presentation/not-fetched",
    })

    assert gate["level"] == "U"
    assert gate["gate_passed"] is False
    assert gate["official_host_match"] is True
    assert gate["official_record"] is False
    assert gate["publication_status"] == "unknown"


def test_fetched_official_metadata_can_pass_academic_gate():
    snapshot = fetching._html_snapshot(
        "https://dl.acm.org/doi/10.1145/1234.5678",
        """
        <html><head>
          <meta name="citation_title" content="Verified Paper">
          <meta name="citation_author" content="Alice">
          <meta name="citation_publication_date" content="2025">
          <meta name="citation_conference_title" content="ACM CCS">
          <meta name="citation_doi" content="10.1145/1234.5678">
        </head><body>Official paper body.</body></html>
        """,
    )

    gate = assess_academic_identity(snapshot)

    assert snapshot["official_record_verified"] is True
    assert gate["level"] == "A1"
    assert gate["gate_passed"] is True
    assert gate["identity_status"] == "officially_aligned"


def test_paper_overrides_are_unverified_supplement(tmp_path):
    repo = PaperArtifactRepository(tmp_path)
    created = PaperIngestService(repo)._persist(
        snapshot={
            "url": "https://evil.example/p.pdf",
            "canonical_url": "https://evil.example/p.pdf",
            "text": "This source contains enough paper text for a reading report.",
            "page_spans": [{"page": 1, "start": 0, "end": 60}],
            "fetch_status": "pdf_ok",
            "source_type": "pdf",
            "official_record_verified": False,
            "verified_academic_metadata": {},
            "source_status": "locked",
        },
        source_url="https://evil.example/p.pdf",
        overrides={
            "title": "Fake",
            "authors": ["Mallory"],
            "year": 2025,
            "venue": "ACM CCS",
            "doi": "10.1234/not-real",
        },
    )

    document = created["result"]["paper_document"]
    assert document["title"] == "Fake"
    assert document["unverified_supplement"]["doi"] == "10.1234/not-real"
    assert document["academic_gate"]["gate_passed"] is False
    assert document["academic_gate"]["doi"] == ""


def test_report_status_and_quotes_are_backend_derived():
    sources = [{
        "source_id": "paper-1",
        "source_url": "https://paper.example/p.pdf",
        "page_start": 1,
        "page_end": 1,
        "text": "The paper studies phishing detection.",
        "evidence_kind": "paper_source",
    }]
    report = _normalize_report(
        {
            "key_questions": [
                {
                    "question": "What is studied?",
                    "answer": "Phishing.",
                    "evidence": [{"exact_quote": "The paper studies phishing detection.", "page": 1}],
                },
                {
                    "question": "What else?",
                    "answer": "A fabricated expansion.",
                    "evidence": [{
                        "exact_quote": "The paper studies phishing detection. Extra fabricated words.",
                        "page": 1,
                    }],
                },
            ],
            "process": [{}],
            "contributions": [{
                "title": "Claimed contribution",
                "description": "Description",
                "evidence": "The paper studies phishing detection. Extra fabricated words.",
            }],
        },
        {"gate_passed": False, "label": "unverified"},
        sources,
    )

    assert report["key_questions"][0]["grounding_status"] == "source_grounded"
    assert report["key_questions"][0]["evidence"][0]["exact_quote"] == "The paper studies phishing detection."
    assert report["key_questions"][1]["grounding_status"] == "unresolved"
    assert report["key_questions"][1]["evidence"] == []
    assert report["process"] == []
    assert report["contributions"][0]["evidence"] == []
    assert report["report_grounding_status"] == "partial"


def test_report_generation_atomically_merges_summary_and_topic_state(monkeypatch, tmp_path):
    repo = PaperArtifactRepository(tmp_path)
    task_id = "paper-task"
    page_text = "Problem statement. Method statement. Contribution statement. Evaluation statement."
    repo.write_result(task_id, {
        "paper_task": True,
        "paper_document": {
            "id": task_id,
            "title": "Paper",
            "source_url": "https://paper.example/p.pdf",
            "pages": [{"page": 1, "text": page_text}],
            "academic_gate": {"gate_passed": False, "label": "unverified"},
            "content_hash": "hash-1",
        },
        "insights": {},
    })
    report_payload = {
        "title": "Report",
        "key_questions": [
            {
                "question": f"Question {index}",
                "answer": "Answer",
                "evidence": [{"exact_quote": quote, "page": 1}],
            }
            for index, quote in enumerate((
                "Problem statement.",
                "Method statement.",
                "Contribution statement.",
                "Evaluation statement.",
            ), start=1)
        ],
        "process": [{"step": "Method", "description": "Method statement."}],
        "contributions": [{
            "title": "Contribution",
            "description": "Contribution statement.",
            "evidence": [{"exact_quote": "Contribution statement.", "page": 1}],
        }],
        "suggested_questions": ["Next question?"],
    }
    started = threading.Event()
    release = threading.Event()

    class FakeCompletions:
        def create(self, **_kwargs):
            started.set()
            assert release.wait(5)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(report_payload)))]
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
    errors = []

    def generate_report():
        try:
            service.generate(task_id=task_id, provider_id="provider", model_name="model")
        except Exception as exc:  # pragma: no cover - assertion below exposes the error
            errors.append(exc)

    worker = threading.Thread(target=generate_report)
    worker.start()
    assert started.wait(5)
    service.save_personal_summary(task_id=task_id, summary="My summary")

    def add_topic_state(payload):
        payload.setdefault("insights", {})["topic_state"] = {"status": "ready"}
        return payload

    repo.update_result(task_id, add_topic_state)
    release.set()
    worker.join(5)

    assert not errors
    saved = repo.read_result(task_id)
    assert saved["insights"]["personal_summary"]["content"] == "My summary"
    assert saved["insights"]["topic_state"]["status"] == "ready"
    assert saved["insights"]["reading_report"]["title"] == "Report"
    assert json.loads(repo.result_path(task_id).read_text(encoding="utf-8"))["paper_task"] is True
    assert not list(tmp_path.glob(".*.tmp"))
