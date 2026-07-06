"""Async MCP client wrapper around Graphify's server (ADR-0002).

Graphify exposes its tools over MCP; Phase 0 talks to it over plain HTTP, the same
way the orchestrator talks to the Verifier
(``services/orchestrator/src/orchestrator/verifier_client.py``) — no MCP SDK
dependency yet. Swapping in a real MCP transport later only touches ``_call_tool``.
"""

import os

import httpx
from platform_telemetry import traced

from context_provider.models import GraphQueryResult, ImpactResult, Node, Path


class GraphifyClientError(Exception):
    """Raised when Graphify's MCP server is unreachable or returns an error."""


class GraphifyClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or os.environ["GRAPHIFY_MCP_URL"]).rstrip("/")

    @traced("mcp.graphify.call", capture_args=True)
    async def _call_tool(self, tool: str, arguments: dict[str, object]) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(f"{self._base_url}/tools/{tool}", json=arguments)
            except httpx.HTTPError as exc:
                raise GraphifyClientError(f"Graphify tool {tool!r} unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise GraphifyClientError(f"Graphify tool {tool!r} failed: {response.text}")
        return response.json()

    async def query_graph(self, query: str) -> GraphQueryResult:
        result = await self._call_tool("query_graph", {"query": query})
        return GraphQueryResult.model_validate(result)

    async def get_node(self, node_id: str) -> Node:
        result = await self._call_tool("get_node", {"node_id": node_id})
        return Node.model_validate(result)

    async def shortest_path(self, from_id: str, to_id: str) -> Path:
        result = await self._call_tool("shortest_path", {"from_id": from_id, "to_id": to_id})
        return Path.model_validate(result)

    async def get_pr_impact(self, pr_ref: str) -> ImpactResult:
        result = await self._call_tool("get_pr_impact", {"pr_ref": pr_ref})
        return ImpactResult.model_validate(result)
