import asyncio
import sys
from collections.abc import AsyncIterator

import pytest_asyncio
from platform_db.session import session_factory
from sqlalchemy.ext.asyncio import AsyncSession

# psycopg's async driver requires a selector-based loop; Windows defaults to Proactor.
if sys.platform == "win32":

    def pytest_asyncio_loop_factories():
        return {"selector": asyncio.SelectorEventLoop}


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
        await session.rollback()
