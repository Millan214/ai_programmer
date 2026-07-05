import os
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def database_url() -> str:
    if url := os.environ.get("DATABASE_URL"):
        return url
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "platform")
    user = os.environ.get("POSTGRES_USER", "platform")
    password = os.environ.get("POSTGRES_PASSWORD", "platform")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


@lru_cache
def engine() -> AsyncEngine:
    return create_async_engine(database_url())


@lru_cache
def session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
