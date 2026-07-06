"""Route tests with an in-memory ``TaskStore`` and a stubbed orchestrator launch — no
Postgres, no real run. The DB-backed path is exercised by the integration test.
"""

# TestClient's httpx responses don't fully resolve under pyright strict; the assertions
# below are the real type check.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from task_api import runner
from task_api.main import app
from task_api.routes import get_store
from task_api.schemas import TaskListItem, TaskStatusResponse

_NOW = datetime(2026, 7, 6, tzinfo=UTC)


class FakeStore:
    def __init__(self) -> None:
        self.tasks: dict[uuid.UUID, TaskStatusResponse] = {}

    async def create_task(
        self, *, repo: str, title: str, description: str, budget_usd: float | None
    ) -> uuid.UUID:
        task_id = uuid.uuid4()
        self.tasks[task_id] = TaskStatusResponse(
            task_id=task_id, repo=repo, title=title, status="queued", created_at=_NOW
        )
        return task_id

    async def get_task(self, task_id: uuid.UUID) -> TaskStatusResponse | None:
        return self.tasks.get(task_id)

    async def list_tasks(self, *, limit: int, offset: int) -> list[TaskListItem]:
        return [
            TaskListItem(
                task_id=t.task_id,
                repo=t.repo,
                title=t.title,
                status=t.status,
                created_at=t.created_at,
            )
            for t in list(self.tasks.values())[offset : offset + limit]
        ]


@pytest.fixture
def store() -> Iterator[FakeStore]:
    fake = FakeStore()
    app.dependency_overrides[get_store] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    calls: list[uuid.UUID] = []
    monkeypatch.setattr(runner, "launch", calls.append)
    return calls


def test_post_creates_task_and_launches_run(
    store: FakeStore, launched: list[uuid.UUID]
) -> None:
    client = TestClient(app)
    response = client.post(
        "/tasks",
        json={"repo": "demo-lib", "title": "add helper", "description": "add a helper fn"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    task_id = uuid.UUID(body["task_id"])  # parses → valid UUID
    # The orchestrator run was enqueued exactly once, for the created task.
    assert launched == [task_id]
    assert task_id in store.tasks


def test_get_returns_task(store: FakeStore, launched: list[uuid.UUID]) -> None:
    client = TestClient(app)
    created = client.post(
        "/tasks", json={"repo": "demo-lib", "title": "t", "description": "d"}
    ).json()
    task_id = created["task_id"]

    response = client.get(f"/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json()["task_id"] == task_id
    assert response.json()["repo"] == "demo-lib"


def test_get_unknown_task_returns_404(store: FakeStore) -> None:
    client = TestClient(app)
    response = client.get(f"/tasks/{uuid.uuid4()}")
    assert response.status_code == 404


def test_list_returns_created_tasks(store: FakeStore, launched: list[uuid.UUID]) -> None:
    client = TestClient(app)
    for i in range(3):
        client.post("/tasks", json={"repo": "demo-lib", "title": f"t{i}", "description": "d"})

    response = client.get("/tasks", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert len(body["tasks"]) == 2
