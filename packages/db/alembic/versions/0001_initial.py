"""initial schema: task, task_session, agent_turn, verifier_run

Revision ID: 0001
Revises:
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("repo", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("budget_usd", sa.Numeric(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "task_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task.id"),
            nullable=False,
        ),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("supervisor_state", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "agent_turn",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_session.id"),
            nullable=False,
        ),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("output_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "verifier_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_session.id"),
            nullable=False,
        ),
        sa.Column("worktree_ref", sa.Text(), nullable=False),
        sa.Column("build", postgresql.JSONB(), nullable=True),
        sa.Column("typecheck", postgresql.JSONB(), nullable=True),
        sa.Column("tests", postgresql.JSONB(), nullable=True),
        sa.Column("coverage", postgresql.JSONB(), nullable=True),
        sa.Column("lint", postgresql.JSONB(), nullable=True),
        sa.Column("scanners", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("verifier_run")
    op.drop_table("agent_turn")
    op.drop_table("task_session")
    op.drop_table("task")
