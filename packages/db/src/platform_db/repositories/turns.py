import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from platform_db.models import AgentTurn


async def create(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    agent: str,
    model: str,
    prompt_version: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal | None = None,
    tool_calls: dict | None = None,
    output_ref: str | None = None,
) -> AgentTurn:
    turn = AgentTurn(
        session_id=session_id,
        agent=agent,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        tool_calls=tool_calls,
        output_ref=output_ref,
    )
    session.add(turn)
    await session.flush()
    return turn


async def get(session: AsyncSession, turn_id: uuid.UUID) -> AgentTurn | None:
    return await session.get(AgentTurn, turn_id)
