"""HTTP routes for the task API (card 09).

Thin: create the row, enqueue the orchestrator run, return the id. The ``TaskStore``
comes through ``Depends(get_store)`` so tests swap in a fake via
``app.dependency_overrides``; ``runner.launch`` is a module attribute tests monkeypatch
so no real orchestrator starts.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from task_api import runner
from task_api.schemas import (
    CreateTaskRequest,
    TaskListResponse,
    TaskResponse,
    TaskStatusResponse,
)
from task_api.store import PostgresTaskStore, TaskStore

router = APIRouter()


def get_store() -> TaskStore:
    return PostgresTaskStore()


@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    body: CreateTaskRequest, store: TaskStore = Depends(get_store)
) -> TaskResponse:
    task_id = await store.create_task(
        repo=body.repo,
        title=body.title,
        description=body.description,
        budget_usd=body.budget_usd,
    )
    runner.launch(task_id)
    return TaskResponse(task_id=task_id, status="queued")


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(
    task_id: uuid.UUID, store: TaskStore = Depends(get_store)
) -> TaskStatusResponse:
    detail = await store.get_task(task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    return detail


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    store: TaskStore = Depends(get_store),
) -> TaskListResponse:
    items = await store.list_tasks(limit=limit, offset=offset)
    return TaskListResponse(tasks=items, limit=limit, offset=offset)
