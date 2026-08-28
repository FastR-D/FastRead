from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.repositories.paper_artifacts import PaperArtifactRepository
from app.services import paper_task_service
from app.services.academic_evidence import assess_academic_identity
from app.services.paper_task_service import PaperTaskService
from app.services.venue_catalog import VENUES


@pytest.mark.parametrize("venue", VENUES, ids=lambda venue: venue.id)
def test_every_enabled_core_venue_uses_the_same_a1_gate(venue):
    gate = assess_academic_identity(
        {
            "url": "https://dl.acm.org/doi/10.1000/example",
            "official_record_verified": True,
            "verified_academic_metadata": {
                "title": "A Formally Published Paper",
                "authors": ["Alice", "Bob"],
                "published_at": "2026",
                "venue": venue.short_name,
                "doi": "10.1000/example",
                "source_url": "https://dl.acm.org/doi/10.1000/example",
            },
        }
    )

    assert gate["gate_passed"] is True
    assert gate["level"] == "A1"
    assert gate["venue"]["id"] == venue.id
    assert gate["venue_track"] == venue.track


def test_withdrawn_core_record_never_passes_gate():
    gate = assess_academic_identity(
        {
            "url": "https://openreview.net/forum?id=withdrawn",
            "registry_record_verified": True,
            "registry_record_url": "https://openreview.net/forum?id=withdrawn",
            "verified_academic_metadata": {
                "title": "Withdrawn Paper",
                "authors": ["Alice"],
                "published_at": "2026",
                "venue": "ICLR 2026",
                "publication_status": "Withdrawn",
                "source_url": "https://openreview.net/forum?id=withdrawn",
            },
        }
    )

    assert gate["gate_passed"] is False
    assert gate["publication_status"] == "withdrawn"
    assert "retracted_or_withdrawn" in gate["warnings"]


def test_task_listing_is_db_authoritative_and_paper_only(monkeypatch, tmp_path):
    artifacts = PaperArtifactRepository(tmp_path)
    artifacts.write_result(
        "paper-a",
        {
            "paper_task": True,
            "paper_document": {"title": "Paper A", "pages": [{"page": 1, "text": "text"}]},
            "insights": {},
        },
    )
    # An orphaned legacy-shaped JSON file must not be merged into /api/tasks.
    artifacts.write_result("orphan", {"platform": "legacy", "title": "orphan"})
    monkeypatch.setattr(
        paper_task_service,
        "list_paper_tasks",
        lambda: [{"task_id": "paper-a", "title": "Paper A"}],
    )

    tasks = PaperTaskService(artifacts).list_tasks()

    assert [task["task_id"] for task in tasks] == ["paper-a"]
    assert all(task["kind"] == "paper" for task in tasks)
    assert all("platform" not in task for task in tasks)


@asynccontextmanager
async def _lifespan(_app):
    yield


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/verification_tasks"),
        ("get", "/api/verification_tasks"),
        ("post", "/api/online_verify"),
        ("post", "/api/download"),
        ("post", "/api/transcribe"),
        ("get", "/api/reading_reports/retired-task/pptx"),
    ],
)
def test_retired_apis_return_404(method, path):
    with TestClient(create_app(lifespan=_lifespan)) as client:
        response = getattr(client, method)(path)

    assert response.status_code == 404
