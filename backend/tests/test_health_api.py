import asyncio
import json

from app.routers.config import sys_health


def test_health_checks_database_and_writable_runtime_storage():
    response = asyncio.run(sys_health())

    assert response.status_code == 200
    payload = json.loads(response.body)["data"]
    assert payload["status"] == "healthy"
    assert payload["checks"]["database"] is True
    assert payload["checks"]["paper_storage"] is True
    assert payload["checks"]["uploads"] is True
    assert set(payload["checks"]) == {"database", "paper_storage", "uploads"}
