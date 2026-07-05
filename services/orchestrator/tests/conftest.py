import asyncio
import sys

# psycopg's async driver requires a selector-based loop; Windows defaults to Proactor.
# Only the integration test touches the DB, but the factory applies to all async tests here.
if sys.platform == "win32":

    def pytest_asyncio_loop_factories() -> dict[str, type[asyncio.AbstractEventLoop]]:
        return {"selector": asyncio.SelectorEventLoop}
