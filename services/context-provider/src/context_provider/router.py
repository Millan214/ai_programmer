"""Routing rule from ADR-0002: symbol queries hit CRG first (cheap, targeted,
~100-350 tokens); neighborhood exploration goes to Graphify's BFS (~1500 tokens).
CRG is only skipped past when it comes back empty — the target repo may not have
reindexed the symbol yet, not a reason to give up on the query.

Defined against ``Protocol``s rather than the concrete ``GraphifyClient``/``CRGClient``
classes so tests can pass fakes without spinning up HTTP servers, matching
``orchestrator.protocols``.
"""

from typing import Literal, Protocol

from platform_telemetry import traced

from context_provider.models import GraphQueryResult, Node, RetrievalResult


class SymbolSearcher(Protocol):
    async def semantic_search_nodes(self, query: str, limit: int = 10) -> list[Node]: ...


class GraphExplorer(Protocol):
    async def query_graph(self, query: str) -> GraphQueryResult: ...


@traced("context_provider.retrieve", capture_args=True)
async def retrieve(
    query: str,
    repo: str,
    mode: Literal["symbol", "explore"],
    *,
    crg: SymbolSearcher,
    graphify: GraphExplorer,
) -> RetrievalResult:
    if mode == "explore":
        result = await graphify.query_graph(query)
        return RetrievalResult(source="graphify", nodes=result.nodes)

    nodes = await crg.semantic_search_nodes(query)
    if nodes:
        return RetrievalResult(source="crg", nodes=nodes)

    result = await graphify.query_graph(query)
    return RetrievalResult(source="graphify", nodes=result.nodes)
