# ADR-0004: OPA (Open Policy Agent) for policy enforcement

## Status

Accepted, 2026-07. Introduced in Phase 2; before then, policies are hardcoded stubs in the orchestrator.

## Context

The platform needs to enforce several categories of policy:

- **Per-agent permissions.** The Security agent may read anything but only write to `/security/*`. The Developer agent may not modify files under `infra/`.
- **Cost caps.** Per-task budget (e.g. $5), per-user daily budget, per-tenant monthly budget.
- **Protected paths.** No writes to `main` or `infra/production/` without human approval.
- **Approval gates.** PRs above a size threshold require human sign-off; PRs from newly-onboarded target repos require sign-off for the first N tasks.
- **Model routing constraints.** Certain tenants pin to certain model providers for compliance.

These policies are org-level concerns that will evolve independently of agent code. Baking them into agents means every rule change is a code change; missed rules are silent security holes.

## Decision

Use **OPA** with **Rego** policies. Policies live in `policies/` at the repo root as versioned Rego files. Every action that could be governed (agent tool call, file write, model selection, PR open, cost accrual) queries OPA before executing.

- Policy queries go through a thin `policy-client` in `packages/shared/` that hits an OPA sidecar over HTTP.
- Policy decisions are persisted to `policy_decision` in Postgres — every deny is auditable.
- Policies are unit-tested with OPA's built-in test runner. Tests run in `make test`.
- A `policies/README.md` documents each policy's rationale, owner, and last review date.

Introduced in Phase 2. Until then, the orchestrator has a `Policies` stub with hardcoded defaults matching what OPA will eventually enforce, so the interface exists from day one and the migration is a backend swap.

## Consequences

- **Policies evolve without redeploying agents.** OPA bundles reload; agent code doesn't move.
- **Auditability is a first-class output.** Every decision is a row. Compliance/security review has data to work from.
- **Rego has a learning curve.** Not the biggest hurdle, but non-zero. Documented patterns in `policies/README.md` mitigate.
- **Operational overhead.** OPA runs as a sidecar in each service, plus a central policy bundle service. More moving parts. Fine at Phase 2+ scale, worth it for the auditability and evolvability.
- **Fits a Three Lines of Defense framing.** Agents in Line 1; OPA + governance UI in Line 2; audit trail + eval harness in Line 3. Useful for internal risk/compliance conversations.

## Alternatives considered

- **Hardcoded policy checks in agent/service code.** Fine for a demo. Every rule change is a code change, every miss is a silent hole. Rejected for anything past Phase 1.
- **Cedar (AWS's policy language).** Similar shape to Rego, less mature ecosystem outside AWS, less MCP/agent tooling. Reasonable alternative if the team already uses Cedar heavily.
- **Custom policy DSL.** Rejected. Reinventing OPA badly.
- **Kubernetes-style admission webhooks.** Wrong shape; those are for cluster resources, not application-layer authorization.

## References

- OPA: https://www.openpolicyagent.org/
- Rego language: https://www.openpolicyagent.org/docs/latest/policy-language/
- Strategy doc §3.7 (governance / policy layer)
- Related ADRs: ADR-0003 (sandbox access gated by OPA), ADR-0006 (Verifier facts feed policy for approval gates)
