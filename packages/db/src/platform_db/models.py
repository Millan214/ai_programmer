import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all platform tables. Models land via 01-postgres-schema.md."""


class Task(Base):
    __tablename__ = "task"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    repo: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(nullable=False)
    budget_usd: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class TaskSession(Base):
    __tablename__ = "task_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task.id"), nullable=False
    )
    phase: Mapped[str] = mapped_column(nullable=False)
    supervisor_state: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AgentTurn(Base):
    __tablename__ = "agent_turn"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_session.id"), nullable=False
    )
    agent: Mapped[str] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(nullable=False)
    prompt_version: Mapped[str] = mapped_column(nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False)
    output_tokens: Mapped[int] = mapped_column(nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    tool_calls: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class VerifierRun(Base):
    __tablename__ = "verifier_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_session.id"), nullable=False
    )
    worktree_ref: Mapped[str] = mapped_column(nullable=False)
    build: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    typecheck: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    tests: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    coverage: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    lint: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    scanners: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
