"""Direct DB reads for e2e assertions.

A synchronous SQLAlchemy engine (psycopg sync driver) against the same compose Postgres —
no async/event-loop juggling inside the sync test body. Reads only; the platform owns writes.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Engine, create_engine, text

_DSN = "postgresql+psycopg://platform:platform@localhost:5432/platform"


def engine() -> Engine:
    return create_engine(_DSN)


@dataclass(frozen=True)
class Turn:
    agent: str
    cost_usd: Decimal | None
    output_ref: str | None


def session_ids(eng: Engine, task_id: str) -> list[uuid.UUID]:
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT id FROM task_session WHERE task_id = :tid"), {"tid": task_id}
        ).all()
    return [row[0] for row in rows]


def agent_turns(eng: Engine, session_ids: list[uuid.UUID]) -> list[Turn]:
    if not session_ids:
        return []
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT agent, cost_usd, output_ref FROM agent_turn "
                "WHERE session_id = ANY(:sids)"
            ),
            {"sids": session_ids},
        ).all()
    return [Turn(agent=r[0], cost_usd=r[1], output_ref=r[2]) for r in rows]


def latest_verifier_run(eng: Engine, session_ids: list[uuid.UUID]) -> dict[str, object] | None:
    if not session_ids:
        return None
    with eng.connect() as conn:
        row = conn.execute(
            text(
                "SELECT build, tests FROM verifier_run WHERE session_id = ANY(:sids) "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"sids": session_ids},
        ).first()
    if row is None:
        return None
    return {"build": row[0], "tests": row[1]}
