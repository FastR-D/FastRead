from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import note


def test_create_verification_task_api_schedules_background(monkeypatch):
    calls = []

    class FakeTasks:
        def create_verification_task(self, **kwargs):
            calls.append(("create", kwargs))
            return {"task_id": "verify-1", "status": "EXTRACTING_CLAIMS", "input": kwargs}

        def execute_verification_task(self, task_id):
            calls.append(("execute", {"task_id": task_id}))

    monkeypatch.setattr(note, "NOTE_TASKS", FakeTasks())
    app = FastAPI()
    app.include_router(note.router)

    response = TestClient(app).post(
        "/verification_tasks",
        json={"text": "鸡蛋中含有超过1500种独特蛋白质。"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "verify-1"
    assert payload["status"] == "EXTRACTING_CLAIMS"
    assert calls[0][0] == "create"
    assert calls[0][1]["max_claims"] == 50
    assert calls[0][1]["verification_depth"] == "deep"
    assert calls[0][1]["source_policy"] == "authoritative"
    assert calls[1] == ("execute", {"task_id": "verify-1"})


def test_verification_task_api_rejects_empty_input():
    app = FastAPI()
    app.include_router(note.router)

    response = TestClient(app).post("/verification_tasks", json={})

    assert response.status_code == 422


def test_rerun_verification_task_api_defaults_to_failed_only(monkeypatch):
    calls = []

    class FakeTasks:
        def rerun_verification_task(self, task_id, retry_failed_only=True):
            calls.append({"task_id": task_id, "retry_failed_only": retry_failed_only})
            return {"ok": True, "data": {"id": task_id}}

    monkeypatch.setattr(note, "NOTE_TASKS", FakeTasks())
    app = FastAPI()
    app.include_router(note.router)

    response = TestClient(app).post("/verification_tasks/task-a/rerun")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == "task-a"
    assert calls == [{"task_id": "task-a", "retry_failed_only": True}]


def test_rerun_verification_task_api_allows_full_rerun(monkeypatch):
    calls = []

    class FakeTasks:
        def rerun_verification_task(self, task_id, retry_failed_only=True):
            calls.append({"task_id": task_id, "retry_failed_only": retry_failed_only})
            return {"ok": True, "data": {"id": task_id}}

    monkeypatch.setattr(note, "NOTE_TASKS", FakeTasks())
    app = FastAPI()
    app.include_router(note.router)

    response = TestClient(app).post(
        "/verification_tasks/task-a/rerun",
        json={"retry_failed_only": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["id"] == "task-a"
    assert calls == [{"task_id": "task-a", "retry_failed_only": False}]


def test_rerun_verification_claim_api(monkeypatch):
    calls = []

    class FakeTasks:
        def rerun_verification_claim(self, task_id, claim_id):
            calls.append({"task_id": task_id, "claim_id": claim_id})
            return {"ok": True, "data": {"id": task_id, "claim_id": claim_id}}

    monkeypatch.setattr(note, "NOTE_TASKS", FakeTasks())
    app = FastAPI()
    app.include_router(note.router)

    response = TestClient(app).post("/verification_tasks/task-a/claims/claim-1-abc/rerun")

    assert response.status_code == 200
    assert response.json()["data"] == {"id": "task-a", "claim_id": "claim-1-abc"}
    assert calls == [{"task_id": "task-a", "claim_id": "claim-1-abc"}]
