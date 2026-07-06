"""Request/response models for the task API (card 09).

Kept separate from the ``TaskStore`` layer so the HTTP contract is one file to read.
``TaskStatusResponse`` folds the task row together with its latest session's phase and
latest verifier run's per-check statuses — the "where is my task" view a poller wants.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class CreateTaskRequest(BaseModel):
    repo: str
    title: str
    description: str
    budget_usd: float | None = None


class TaskResponse(BaseModel):
    """POST /tasks — the run is enqueued; poll GET /tasks/{id} for progress."""

    task_id: uuid.UUID
    status: str


class VerifierSummary(BaseModel):
    """Per-check statuses from the latest verifier run, or None where it didn't run."""

    build: str | None = None
    typecheck: str | None = None
    tests: str | None = None
    lint: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: uuid.UUID
    repo: str
    title: str
    status: str
    phase: str | None = None
    verifier: VerifierSummary | None = None
    created_at: datetime


class TaskListItem(BaseModel):
    task_id: uuid.UUID
    repo: str
    title: str
    status: str
    created_at: datetime


class TaskListResponse(BaseModel):
    tasks: list[TaskListItem]
    limit: int
    offset: int
