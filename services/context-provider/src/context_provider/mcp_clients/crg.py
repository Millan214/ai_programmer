"""Async MCP client wrapper around `code-review-graph`'s server (ADR-0002).

Same HTTP-shaped MCP call convention as ``context_provider.mcp_clients.graphify``.
CRG's real tool surface is allow-listed via ``CRG_TOOLS`` per ADR-0002; only the
tools the router uses are wrapped here.
"""

import os
from typing import cast

import httpx

from context_provider.models import Community, ImpactResult, Node


class CRGClientError(Exception):
    """Raised when CRG's MCP server is unreachable or returns an error."""


class CRGClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or os.environ["CRG_MCP_URL"]).rstrip("/")

    async def _call_tool(self, tool: str, arguments: dict[str, object]) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(f"{self._base_url}/tools/{tool}", json=arguments)
            except httpx.HTTPError as exc:
                raise CRGClientError(f"CRG tool {tool!r} unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise CRGClientError(f"CRG tool {tool!r} failed: {response.text}")
        return response.json()

    async def semantic_search_nodes(self, query: str, limit: int = 10) -> list[Node]:
        result = await self._call_tool("semantic_search_nodes", {"query": query, "limit": limit})
        nodes = cast(list[object], result["nodes"])
        return [Node.model_validate(n) for n in nodes]

    async def get_impact_radius(self, symbol: str) -> ImpactResult:
        result = await self._call_tool("get_impact_radius", {"symbol": symbol})
        return ImpactResult.model_validate(result)

    async def list_communities(self) -> list[Community]:
        result = await self._call_tool("list_communities", {})
        communities = cast(list[object], result["communities"])
        return [Community.model_validate(c) for c in communities]
