"""End-to-end route test against real Postgres (``make up``). The orchestrator launch is
still stubbed — this pins the DB-backed ``PostgresTaskStore`` read/write path, not a full
run. Marked ``integration``; skipped by default.
"""

# TestClient's httpx responses don't fully resolve under pyright strict; the assertions
# below are the real type check.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

import uuid

import pytest
from fastapi.testclient import TestClient
from task_api import runner
from task_api.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def no_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    def _noop(task_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(runner, "launch", _noop)


def test_create_get_list_round_trip_against_postgres(no_launch: None) -> None:
    client = TestClient(app)

    created = client.post(
        "/tasks",
        json={
            "repo": "demo-lib",
            "title": "integration task",
            "description": "d",
            "budget_usd": 1.5,
        },
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]
    uuid.UUID(task_id)  # valid

    fetched = client.get(f"/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "integration task"
    assert fetched.json()["status"] == "queued"

    listed = client.get("/tasks", params={"limit": 10})
    assert listed.status_code == 200
    assert any(row["task_id"] == task_id for row in listed.json()["tasks"])
