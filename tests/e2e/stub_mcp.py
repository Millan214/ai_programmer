"""A stub retrieval backend standing in for Graphify + CRG in the e2e (card 11).

The card lists "demo repo with Graphify + CRG indexed" as a prereq, but standing up those
MCP servers is out of Phase 0 scope — card 07 built the *client* wrappers against a server
contract, not the servers. This stub serves that contract (the `/tools/{tool}` shape the
Context Provider's clients POST to) and returns empty results, so retrieval succeeds and
returns nothing. That's enough for the smoke task: its description names the exact files
and signatures, so the Developer works from the plan/repo-map hints rather than retrieval.

Run: ``uvicorn stub_mcp:app --port 8009``.
"""

from fastapi import FastAPI

app = FastAPI(title="Stub MCP (Graphify + CRG)")


@app.post("/tools/query_graph")
async def query_graph() -> dict[str, object]:
    # Graphify's GraphQueryResult shape.
    return {"nodes": [], "edges": []}


@app.post("/tools/semantic_search_nodes")
async def semantic_search_nodes() -> dict[str, object]:
    # CRG's semantic_search_nodes shape.
    return {"nodes": []}
