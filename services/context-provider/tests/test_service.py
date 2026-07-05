"""HTTP surface test — monkeypatches the client factories so this doesn't need
Graphify/CRG running. Real transport is covered by ``test_service_integration.py``.
"""

# httpx's ``Client.post`` return type doesn't fully resolve under pyright strict, so
# `response` and everything derived from it comes back as Unknown; the assertions
# below are the actual type check.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

import pytest
from context_provider.models import GraphQueryResult, Node
from context_provider.service import app
from fastapi.testclient import TestClient

client = TestClient(app)


class _FakeCRG:
    async def semantic_search_nodes(self, query: str, limit: int = 10) -> list[Node]:
        return [Node(id="hasPermission", label="hasPermission", kind="function")]


class _FakeGraphify:
    async def query_graph(self, query: str) -> GraphQueryResult:
        return GraphQueryResult(nodes=[], edges=[])


def test_retrieve_symbol_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("context_provider.service._crg_client", lambda: _FakeCRG())
    monkeypatch.setattr("context_provider.service._graphify_client", lambda: _FakeGraphify())

    response = client.post(
        "/retrieve", json={"query": "hasPermission", "repo": "demo-lib", "mode": "symbol"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "crg"
    assert body["nodes"][0]["id"] == "hasPermission"
