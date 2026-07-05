"""Integration test against real Graphify + CRG MCP servers, indexed over
``target-repos/demo-lib/`` (see 07-context-provider.md's prereqs). Skipped unless
both MCP URLs are configured — Phase 0 doesn't stand these servers up in CI.
"""

import os

import pytest
from context_provider.mcp_clients.crg import CRGClient
from context_provider.mcp_clients.graphify import GraphifyClient
from context_provider.router import retrieve

pytestmark = pytest.mark.integration

GRAPHIFY_URL = os.environ.get("GRAPHIFY_MCP_URL")
CRG_URL = os.environ.get("CRG_MCP_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not GRAPHIFY_URL or not CRG_URL,
    reason="GRAPHIFY_MCP_URL / CRG_MCP_URL not configured",
)
async def test_retrieve_known_symbol_returns_non_empty_result() -> None:
    crg = CRGClient(CRG_URL)
    graphify = GraphifyClient(GRAPHIFY_URL)

    result = await retrieve(
        "hasPermission", "demo-lib", "symbol", crg=crg, graphify=graphify
    )

    assert result.nodes
