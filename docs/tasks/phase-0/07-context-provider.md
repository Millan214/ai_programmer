# Task 07 — Context Provider v0 (Graphify + CRG)

## Context

The Context Provider is the single retrieval gateway (`CLAUDE.md` non-negotiable #2). No agent reads files directly. Phase 0 scope: wrap Graphify and CRG as MCP clients, expose a simple `retrieve(query)` interface. Fusion, reranking, budget management, LSP tier, git signal — all Phase 1.

Read ADR-0002 before starting.

## Prereqs

- Scaffold complete.
- Demo target repo present at `target-repos/demo-lib/` with Graphify and CRG installed and indexed:
  ```bash
  cd target-repos/demo-lib
  uv tool install graphifyy code-review-graph
  /graphify .                          # produces graphify-out/
  code-review-graph init                # produces .code-review-graph/
  git add graphify-out/ .code-review-graph/
  git commit -m "chore: initial graph indices"
  ```

## Scope

Files to create in `services/context-provider/`:

- `src/context_provider/mcp_clients/graphify.py`:
  - Async MCP client wrapper around Graphify's server.
  - Exposes typed methods for the tools we use: `query_graph(query: str) -> GraphQueryResult`, `get_node(node_id: str) -> Node`, `shortest_path(from_id: str, to_id: str) -> Path`, `get_pr_impact(pr_ref: str) -> ImpactResult`.
  - Reads `GRAPHIFY_MCP_URL` from env.
- `src/context_provider/mcp_clients/crg.py`:
  - Async MCP client wrapper around CRG's server.
  - Typed methods for: `semantic_search_nodes(query: str, limit: int = 10) -> list[Node]`, `get_impact_radius(symbol: str) -> ImpactResult`, `list_communities() -> list[Community]`.
  - Reads `CRG_MCP_URL` from env.
- `src/context_provider/router.py`:
  - `async def retrieve(query: str, repo: str, mode: Literal["symbol", "explore"]) -> RetrievalResult`:
    - `mode="symbol"` → CRG first (`semantic_search_nodes`), fallback to Graphify `query_graph` if empty.
    - `mode="explore"` → Graphify `query_graph` with BFS depth 2.
  - Encodes the routing rule from ADR-0002.
- `src/context_provider/models.py` — Pydantic models for results, unifying Graphify and CRG shapes.
- `src/context_provider/service.py` — FastAPI with `POST /retrieve` body `{"query": "...", "repo": "...", "mode": "symbol|explore"}`.
- `src/context_provider/main.py` — uvicorn entrypoint.
- `tests/test_router.py`:
  - Mocked MCP clients: `retrieve(mode="symbol")` calls CRG first, only falls back to Graphify on empty result.
  - `retrieve(mode="explore")` calls Graphify directly.
- `tests/test_service_integration.py`:
  - Real Graphify + CRG running against `target-repos/demo-lib/`. Marked `@pytest.mark.integration`. Skipped if MCP URLs not set.
  - Query a known symbol (e.g. `hasPermission` if present) returns non-empty result.

## Success criteria

```bash
cd services/context-provider
pytest -q                              # exit 0

# Run Graphify + CRG MCP servers pointing at demo-lib.
# See their READMEs for how to serve. In env:
export GRAPHIFY_MCP_URL=http://localhost:8010
export CRG_MCP_URL=http://localhost:8011

uvicorn context_provider.main:app --port 8002 &
curl -X POST http://localhost:8002/retrieve \
  -H 'content-type: application/json' \
  -d '{"query": "hasPermission", "repo": "demo-lib", "mode": "symbol"}'
# Returns non-empty results from CRG.
```

## Non-goals

- **No LSP tier.** Phase 1.
- **No git signal (blame, co-change).** Phase 1.
- **No reranker.** Results returned in order given by CRG / Graphify. Fusion + rerank is Phase 1.
- **No Context Budget Manager.** Every call returns everything. Budget enforcement is Phase 1.
- **No caching.** Every call round-trips to the MCP servers.
- **No ADR overlay.** Phase 2.
- **No multi-repo support.** Single target repo assumed. Multi-repo is Phase 4.
- **No prompt-payload assembly.** `retrieve` returns raw results; agents format them into prompt context for now. Curated prompt payloads are a Phase 1 concern once budgets exist.

## Effort

~4 hours.

## Notes

_(fill in as you go — including any surprises with MCP client libraries, transport modes, tool schemas)_
