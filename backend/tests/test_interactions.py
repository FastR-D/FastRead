import json

from app.routers import interactions
from app.services.auth import AccountPrincipal


def _payload(response):
    return json.loads(response.body.decode("utf-8"))


def test_push_contract_is_idempotent_and_returns_workspace_route(monkeypatch):
    receipts = {}
    monkeypatch.setattr(interactions, "get_receipt", lambda account_id, operation, key: receipts.get((account_id, operation, key)))
    monkeypatch.setattr(interactions.PAPERS, "ingest_url", lambda *, url: {"task_id": "paper-123"})
    monkeypatch.setattr(interactions.PAPER_TASKS, "update_collection", lambda **kwargs: kwargs)

    def save_receipt(account_id, operation, key, request_hash, response):
        receipts[(account_id, operation, key)] = {
            "request_hash": request_hash,
            "response": response,
        }

    monkeypatch.setattr(interactions, "save_receipt", save_receipt)
    request = interactions.PushRequest(
        paper_url="https://example.org/papers/123",
        tags=["micro-benchmarking"],
    )
    account = AccountPrincipal(account_id="local", auth_source="local_desktop")

    first = _payload(interactions.push_paper(request, account, "release-test-key"))["data"]
    replay = _payload(interactions.push_paper(request, account, "release-test-key"))["data"]

    assert first["open_path"] == "/workspace?task_id=paper-123"
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True


def test_get_contract_filters_by_tags_and_returns_workspace_route(monkeypatch):
    monkeypatch.setattr(
        interactions,
        "list_paper_tasks",
        lambda: [
            {
                "task_id": "paper-123",
                "title": "Reliable Evaluation",
                "authors": ["Ada Lovelace"],
                "year": 2024,
                "collection_tags": ["Evaluation", "LLM"],
            },
            {
                "task_id": "paper-456",
                "title": "Unrelated Paper",
                "authors": [],
                "year": 2020,
                "collection_tags": ["vision"],
            },
        ],
    )

    response = interactions.get_papers(
        interactions.GetRequest(tags=["evaluation"], limit=20),
        AccountPrincipal(account_id="local", auth_source="local_desktop"),
    )
    papers = _payload(response)["data"]["papers"]

    assert len(papers) == 1
    assert papers[0]["task_id"] == "paper-123"
    assert papers[0]["open_path"] == "/workspace?task_id=paper-123"
