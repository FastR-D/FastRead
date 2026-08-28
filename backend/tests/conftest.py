import pytest


@pytest.fixture(autouse=True)
def isolate_paper_task_persistence(monkeypatch):
    """Artifact-focused tests must never insert fixture tasks into the active DB."""
    monkeypatch.setattr(
        "app.services.paper_ingest_service.upsert_paper_task",
        lambda payload: {**payload},
    )
