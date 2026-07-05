# ADR-0003: Firecracker microVMs for sandbox execution (Docker in Phase 0)

## Status

Accepted, 2026-07. Phase 0 uses Docker; Firecracker migration is a Phase 1 task.

## Context

Agents execute code they wrote themselves: running builds, tests, typecheckers, linters, and arbitrary tool commands the Developer agent decides to invoke. This must be isolated from:

- The orchestrator's process and filesystem.
- The user's credentials, secrets, and cloud environment.
- Other tenants' code and data (Phase 3).
- Each other, if parallel tasks run on the same repo.

The isolation model is a foundational decision. Options range from "Docker container per task" (weak isolation, cheap) to "Firecracker microVM per task attempt" (strong isolation, cheap enough at scale) to "hosted product like E2B or Modal" (fastest to bootstrap, vendor dependency).

## Decision

Two-stage adoption:

- **Phase 0 — Docker.** A single Docker container per task, with a git worktree bind-mounted, dependencies pre-installed in the image. Sandbox controller in `services/sandbox/` spawns and reaps containers.
- **Phase 1 — Firecracker microVMs**, via Fly Machines (managed) or self-hosted. Each task attempt gets a fresh microVM with a git worktree checked out and dependencies pre-warmed via a base snapshot. Cold-start target: <2s.

**E2B is the Phase 0 fallback** if Docker's isolation feels inadequate for testing agents against untrusted-looking generated code. Same interface (sandbox controller); different backend.

Both phases share the same `Sandbox` interface in `services/sandbox/`, so migration is a backend swap, not an interface change.

## Consequences

- **Phase 0 stays simple.** Docker is universally understood, easy to debug, works locally without infra changes.
- **Docker's isolation is weak.** A malicious or misbehaving process inside the container can reach the host in more ways than a Firecracker microVM. Fine while everything is single-tenant and the sandbox runs on a dev machine; not fine when multiple tenants share a host.
- **Firecracker adds real infra.** Either a Fly Machines account (managed, cheapest to start) or self-hosted on bare metal / EC2 metal. Both are meaningful commitments.
- **Base-image / base-snapshot management becomes a subsystem.** Common stacks (Node, Python, Go, Rust) get pre-warmed images so cold starts stay under 2s. Ownership of these images lives in `services/sandbox/`.
- **Secret handling is easier to get right.** The sandbox never receives repo secrets. The Verifier and merge coordinator hold credentials; the sandbox holds only code and generated artifacts. This is enforceable by OPA policy from Phase 2.

## Alternatives considered

- **Docker only, all phases.** Cheapest, weakest isolation. Fine if the platform stays single-tenant with trusted operators. Rejected as a long-term stance because multi-tenancy is on the roadmap (Phase 3).
- **gVisor / Kata.** Stronger than Docker, weaker than Firecracker, moderate overhead. Reasonable intermediate. Rejected because Firecracker via Fly Machines is roughly the same effort at higher isolation.
- **E2B as the permanent choice.** Fastest to run, but third-party dependency for a foundational subsystem. Kept as Phase 0 fallback and as a serious option if self-hosting Firecracker becomes a distraction.
- **Modal.** Similar shape to E2B, more general-purpose. Same tradeoffs.
- **No sandbox (run in orchestrator process).** Rejected on isolation grounds.

## References

- Firecracker: https://firecracker-microvm.github.io/
- Fly Machines: https://fly.io/docs/machines/
- E2B: https://e2b.dev/
- Strategy doc §3.5 (ephemeral sandbox design)
- Related ADRs: ADR-0004 (OPA gates what the sandbox can access), ADR-0006 (Verifier runs inside or alongside the sandbox)
