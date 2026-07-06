import asyncio
import sys

# psycopg's async driver needs a selector-based loop on Windows; the integration test is
# the only DB-touching one but the factory applies to all async tests.
if sys.platform == "win32":

    def pytest_asyncio_loop_factories() -> dict[str, type[asyncio.AbstractEventLoop]]:
        return {"selector": asyncio.SelectorEventLoop}
