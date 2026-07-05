"""Unit tests for the routing rule (ADR-0002): fakes stand in for CRG/Graphify so
no HTTP servers are needed. Real transport is exercised by
``test_service_integration.py``.
"""

import pytest
from context_provider.models import GraphQueryResult, Node
from context_provider.router import retrieve


def _node(node_id: str) -> Node:
    return Node(id=node_id, label=node_id, kind="function")


class FakeCRG:
    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = nodes
        self.calls: list[str] = []

    async def semantic_search_nodes(self, query: str, limit: int = 10) -> list[Node]:
        self.calls.append(query)
        return self._nodes


class FakeGraphify:
    def __init__(self, nodes: list[Node]) -> None:
        self._nodes = nodes
        self.calls: list[str] = []

    async def query_graph(self, query: str) -> GraphQueryResult:
        self.calls.append(query)
        return GraphQueryResult(nodes=self._nodes, edges=[])


@pytest.mark.asyncio
async def test_symbol_mode_uses_crg_when_it_has_results() -> None:
    crg = FakeCRG([_node("hasPermission")])
    graphify = FakeGraphify([])

    result = await retrieve("hasPermission", "demo-lib", "symbol", crg=crg, graphify=graphify)

    assert result.source == "crg"
    assert [n.id for n in result.nodes] == ["hasPermission"]
    assert crg.calls == ["hasPermission"]
    assert graphify.calls == []


@pytest.mark.asyncio
async def test_symbol_mode_falls_back_to_graphify_when_crg_empty() -> None:
    crg = FakeCRG([])
    graphify = FakeGraphify([_node("hasPermission")])

    result = await retrieve("hasPermission", "demo-lib", "symbol", crg=crg, graphify=graphify)

    assert result.source == "graphify"
    assert [n.id for n in result.nodes] == ["hasPermission"]
    assert crg.calls == ["hasPermission"]
    assert graphify.calls == ["hasPermission"]


@pytest.mark.asyncio
async def test_explore_mode_calls_graphify_directly() -> None:
    crg = FakeCRG([_node("unused")])
    graphify = FakeGraphify([_node("neighborhood")])

    result = await retrieve("hasPermission", "demo-lib", "explore", crg=crg, graphify=graphify)

    assert result.source == "graphify"
    assert [n.id for n in result.nodes] == ["neighborhood"]
    assert crg.calls == []
    assert graphify.calls == ["hasPermission"]
