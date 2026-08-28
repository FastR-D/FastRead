from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.routers import note
from app.routers.note import CollectionUpdateRequest
from app.services.paper_task_service import PaperTaskService
from app.utils.collections import DEFAULT_COLLECTION_FOLDER, require_collection_folder


def test_collection_request_normalizes_name_and_rejects_empty_or_long_names():
    request = CollectionUpdateRequest(collection_folder="  本周   必读  ")
    assert request.collection_folder == "本周 必读"

    with pytest.raises(ValidationError, match="收藏夹名称不能为空"):
        CollectionUpdateRequest(collection_folder="  \n ")
    with pytest.raises(ValidationError, match="80"):
        CollectionUpdateRequest(collection_folder="a" * 81)


def test_delete_collection_reassigns_members_in_one_dao_operation(monkeypatch):
    calls = []

    def fake_delete(folder: str, *, replacement_folder: str):
        calls.append((folder, replacement_folder))
        return ["paper-1", "paper-2"]

    monkeypatch.setattr("app.services.paper_task_service.delete_paper_collection", fake_delete)
    service = PaperTaskService(artifacts=SimpleNamespace())

    result = service.delete_collection("  组会   必读 ")

    assert calls == [("组会 必读", DEFAULT_COLLECTION_FOLDER)]
    assert result == {
        "collection_folder": "组会 必读",
        "replacement_folder": DEFAULT_COLLECTION_FOLDER,
        "updated_task_ids": ["paper-1", "paper-2"],
        "updated_count": 2,
    }


def test_default_collection_cannot_be_deleted(monkeypatch):
    delete = pytest.MonkeyPatch()
    try:
        mocked = lambda *args, **kwargs: pytest.fail("DAO must not run")
        delete.setattr("app.services.paper_task_service.delete_paper_collection", mocked)
        service = PaperTaskService(artifacts=SimpleNamespace())
        with pytest.raises(ValueError, match="默认收藏夹不能删除"):
            service.delete_collection(DEFAULT_COLLECTION_FOLDER)
    finally:
        delete.undo()


def test_delete_collection_route_reports_updated_papers(monkeypatch):
    monkeypatch.setattr(
        note,
        "PAPER_TASKS",
        SimpleNamespace(delete_collection=lambda folder: {
            "collection_folder": require_collection_folder(folder),
            "replacement_folder": DEFAULT_COLLECTION_FOLDER,
            "updated_task_ids": ["paper-1"],
            "updated_count": 1,
        }),
    )

    response = note.delete_collection_folder("专题")
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["data"]["updated_task_ids"] == ["paper-1"]
