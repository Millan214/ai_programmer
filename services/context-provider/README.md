# platform-context-provider

Single retrieval gateway wrapping Graphify + CRG for all agents (ADR-0002). No agent
reads files directly — every retrieval goes through `POST /retrieve` here.

`context_provider.router.retrieve` encodes the routing rule: `mode="symbol"` queries
hit CRG's `semantic_search_nodes` first (cheap, targeted) and only fall back to
Graphify's `query_graph` when CRG comes back empty; `mode="explore"` goes straight to
Graphify for BFS-style neighborhood traversal.

`context_provider.mcp_clients.graphify` / `.crg` are thin async HTTP wrappers around
each project's MCP server — same shelling-out-over-HTTP convention as
`services/orchestrator/src/orchestrator/verifier_client.py`, not a bespoke MCP SDK
dependency. `GRAPHIFY_MCP_URL` / `CRG_MCP_URL` configure them.

Phase 0 non-goals (see `07-context-provider.md`): no LSP tier, no git signal, no
reranker/fusion, no context budget manager, no caching, no ADR overlay, no
multi-repo support.

## Run the tests

```bash
pytest -q                    # unit tests, mocked CRG/Graphify — no servers required
pytest -q -m integration      # needs real Graphify + CRG MCP servers indexed over
                              # target-repos/demo-lib/, with GRAPHIFY_MCP_URL / CRG_MCP_URL set
```

## Serve

```bash
export GRAPHIFY_MCP_URL=http://localhost:8010
export CRG_MCP_URL=http://localhost:8011
uvicorn context_provider.main:app --port 8003
```

Filled in by [`07-context-provider.md`](../../docs/tasks/phase-0/07-context-provider.md).
