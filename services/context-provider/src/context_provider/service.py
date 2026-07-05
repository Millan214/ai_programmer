"""The Context Provider's FastAPI surface: ``POST /retrieve``.

Clients are constructed lazily per request from ``GRAPHIFY_MCP_URL``/``CRG_MCP_URL``
so importing this module doesn't require either env var to be set (unit tests
monkeypatch the factories; only the integration tests need real servers running).
"""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from context_provider.mcp_clients.crg import CRGClient
from context_provider.mcp_clients.graphify import GraphifyClient
from context_provider.models import RetrievalResult
from context_provider.router import retrieve

app = FastAPI(title="Context Provider")


class RetrieveRequest(BaseModel):
    query: str
    repo: str
    mode: Literal["symbol", "explore"]


def _crg_client() -> CRGClient:
    return CRGClient()


def _graphify_client() -> GraphifyClient:
    return GraphifyClient()


@app.post("/retrieve")
async def retrieve_endpoint(request: RetrieveRequest) -> RetrievalResult:
    return await retrieve(
        request.query,
        request.repo,
        request.mode,
        crg=_crg_client(),
        graphify=_graphify_client(),
    )
