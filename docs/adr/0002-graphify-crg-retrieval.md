# ADR-0002: Graphify + `code-review-graph` (CRG) as the code-intelligence layer

## Status

Accepted, 2026-07. Contract-test both projects' MCP surfaces on every dependency bump; re-evaluate if either project stalls for >6 months.

## Context

Agents need to understand codebases without burning tokens re-reading files on every question. The naive path — vector RAG over file chunks — loses structural information (who calls whom, which module depends on which) and doesn't scale token-wise on real repos. The original blueprint proposed a monolithic "Codebase Memory MCP" that would handle symbol lookup, dependency graph, call graph, semantic search, and architecture summaries all at once. That bundles very different backends (LSP, tree-sitter, embeddings, LLM summarization) with different freshness and cost profiles.

Two mature open-source projects now cover most of this ground:

- **Graphify** (safishamsi/graphify) — tree-sitter AST across 33+ languages, LLM-driven semantic extraction, Leiden clustering, MCP server, incremental subgraph updates on file change, confidence tags (EXTRACTED/INFERRED/AMBIGUOUS) on every edge. Handles code + docs + PDFs + diagrams natively. MIT licensed, YC-backed.
- **`code-review-graph` (CRG)** — SQLite-backed AST graph, embedding-based semantic search, blast-radius analysis, ~25 MCP tools (allow-listable). Sub-second incremental updates. Complementary to Graphify: CRG serves symbol queries at ~100-350 tokens vs Graphify's ~1500 for BFS-style exploration.

## Decision

Adopt **Graphify + CRG** as the concrete implementation of the symbol/AST + knowledge-graph tier and the symbol-lookup + semantic-search tier. Wrap both in our own **Context Provider**, which is the single retrieval gateway for all agents.

Split of responsibilities:

- **Graphify** — symbol/AST + knowledge graph + docs/PDFs/diagrams. MCP tools: `query_graph`, `get_node`, `shortest_path`, `get_pr_impact`. Used for neighborhood exploration and cross-modal traversal.
- **CRG** — symbol lookup + semantic search + blast-radius. MCP tools (allow-listed via `CRG_TOOLS`): `semantic_search_nodes`, `query_graph`, `get_impact_radius`, `list_communities`. Used for cheap targeted queries.
- **LSP tier (built by us, Phase 1)** — definitions, references, hovers when tree-sitter can't disambiguate.
- **Git signal (built by us, Phase 1)** — blame, recency, co-change over `libgit2`.
- **ADR overlay (built by us, Phase 2)** — Kùzu or Postgres graph tables for ADR nodes and their edges to Graphify code-symbol node IDs. Joined at query time. See §3.9 of the strategy doc.

Routing rule inside Context Provider: symbol queries → CRG first; neighborhood exploration → Graphify BFS; LSP only when structural precision matters.

Both projects' state is committed alongside the code in each target repo (`graphify-out/` and `.code-review-graph/`), not in this platform repo. Git hooks trigger incremental updates.

## Consequences

- **Phase 0 velocity gain is large.** No custom tree-sitter indexer, no bespoke graph store, no embedding pipeline for code. `07-context-provider.md` becomes a wrapper task, not a build task.
- **Phase 4 shrinks substantially.** The "cross-repository knowledge graph" work becomes "federate multiple repos' Graphify graphs behind one Context Provider", not "design and build a graph system".
- **Dependency risk on two young projects.** Mitigations: pin versions; contract-test the MCP tool surface; keep Context Provider abstraction thin so a swap-out is possible; retain `graph.json` and SQLite files under version control so historical snapshots survive project stalls.
- **ADR-as-first-class-node** is not native to Graphify. We overlay in Phase 2 and evaluate contributing upstream in Phase 4.
- **Non-code semantic content** (e.g. user-uploaded PDFs not committed to the repo) still needs pgvector or similar; CRG covers code embeddings only.
- **Multi-tenant isolation gets easier** since each target repo owns its own graph state. Cross-tenant graph queries are impossible by construction.

## Alternatives considered

- **Build a custom tree-sitter + embedding stack.** ~2-3 months of work replicating what Graphify + CRG already do well. Rejected. If both projects vanished tomorrow, the fallback is Sourcegraph (heavier ops) or building the minimum ourselves, not "reject at the start".
- **Sourcegraph.** Mature, feature-rich, but heavier to self-host and less MCP-native. Would work; more infra for less agent-specific integration. Kept as a plan-B option.
- **Vector search only (pgvector + chunking).** Loses all structural information. Fails on "who calls X" queries. Fine for exploratory retrieval within a fusion strategy; wrong as the sole retrieval.
- **Neo4j / Kùzu populated by our own indexer.** Reasonable if we already had the indexer; we don't, and Graphify's incremental-update semantics are non-trivial to replicate. Kept for the ADR overlay only.
- **LSP-only retrieval.** Precise for symbols but no semantic search, no docs, no cross-modal. Necessary tier, insufficient alone.

## References

- Graphify: https://github.com/safishamsi/graphify
- `code-review-graph`: (SQLite-backed AST graph with ~25 MCP tools; see dev.to guide referenced in strategy doc §3.3)
- Strategy doc §2 (structural weaknesses), §3.3 (multi-tier retrieval), §3.9 (knowledge graph)
- Related ADRs: ADR-0006 (verifier uses Graphify's confidence tags in structured facts)
