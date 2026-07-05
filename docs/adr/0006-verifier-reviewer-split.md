# ADR-0006: Verifier (facts) separate from Reviewer (interpretation)

## Status

Accepted, 2026-07. Verifier lands in Phase 0; Reviewer in Phase 2.

## Context

The original blueprint bundled "correctness, maintainability, bugs" under a single Reviewer agent — an LLM reading code and producing review comments. LLM review without ground truth is opinion. It hallucinates broken tests that pass, cites type errors that don't exist, and misses real regressions because it never ran the code.

The failure mode is predictable: the Reviewer says "this looks good; tests will pass" and the tests don't pass. Or the Reviewer flags a bug that isn't a bug. Both are cheap noise that erode trust in the platform.

The problem isn't the LLM; the problem is asking a language model to answer questions with factual answers when a factual subsystem could answer them exactly.

## Decision

Split code review into two subsystems:

### Verifier — deterministic, factual

A subsystem (not an agent) that runs actual tools and returns structured facts:

- Build: `pnpm build`, `cargo build`, etc.
- Typecheck: `tsc --noEmit`, `pyright`, `cargo check`.
- Lint: `eslint`, `ruff`, `clippy`.
- Unit and integration tests, with pass/fail and coverage delta.
- Security scanners: Semgrep, Trivy, gitleaks (Phase 2+).
- Dependency audit: `npm audit`, `pip-audit` (Phase 2+).

Returns structured JSON:

```json
{
  "build": {"status": "pass"},
  "typecheck": {"status": "fail", "errors": [{"file": "...", "line": 42, "message": "..."}]},
  "tests": {"total": 13, "passed": 12, "failed": 1, "failures": [...]},
  "coverage": {"delta": -1.2, "files_below_threshold": ["..."]},
  "lint": {"errors": 0, "warnings": 3},
  "scanners": {...}
}
```

Lives in `services/verifier/`. HTTP endpoint. Owns no LLM.

### Reviewer — interpretive, LLM-driven

An agent (Phase 2) that reads the Verifier's structured facts plus the code diff and produces:

- Interpretation of what the failures mean.
- Judgment on correctness, maintainability, readability.
- Suggested changes.
- A verdict (approve / request changes / block).

**Non-negotiable constraint:** the Reviewer may not claim a factual thing (build passes, tests pass, coverage is X%) that the Verifier hasn't confirmed. Reviewer prompts are structured to require citing Verifier facts by field. Reviewer output is validated against Verifier output before it's persisted; any claim that contradicts Verifier is treated as a hallucination and the review is regenerated.

## Consequences

- **Reviewer prompts get factual scaffolding.** The Verifier's structured output is the starting context; the Reviewer's job is interpretation on top of it. This constrains the LLM in exactly the way that most reduces hallucination.
- **Verifier is a hot path.** Every Build → Verify transition runs it. Must be fast (target: <60s for a typical Phase 0 task). Caching by content hash on unchanged files helps.
- **Verifier failures are structured, not free-form.** Downstream agents (Developer, Reviewer, Supervisor) can pattern-match on structured fields (`typecheck.errors[]`) instead of parsing prose.
- **Adding a new check is a Verifier concern, not a Reviewer concern.** Semgrep integration in Phase 2 is a Verifier extension; the Reviewer just sees another field in the facts.
- **Class of bugs eliminated:** hallucinated review comments, false-positive test-pass claims, invented type errors.
- **Class of bugs remaining:** the Verifier itself can be wrong (misconfigured, wrong test runner, wrong project root). That's a config issue, not a hallucination issue, and it's much cheaper to debug.

## Alternatives considered

- **Single LLM Reviewer, no Verifier.** The original blueprint's shape. Rejected because factual questions get non-factual answers.
- **Verifier only, no Reviewer.** Loses the maintainability/readability judgment layer. Rejected for anything past Phase 1 — Verifier facts alone don't catch "this is correct but hard to read" or "this design will bite us later".
- **Hybrid single agent that runs tools and interprets.** Same LLM does both. Works but conflates two very different failure modes and doesn't give downstream agents structured facts to work with.
- **Verifier as an LLM with tool use.** Rejected — the whole point is determinism. Tool-use loops are non-deterministic, harder to cache, harder to reason about.

## References

- Strategy doc §3.2 (Verifier / Reviewer split)
- Related ADRs: ADR-0001 (LangGraph orchestrates the Build → Verify transition), ADR-0005 (Supervisor consumes Verifier facts to decide next action), ADR-0002 (Graphify confidence tags feed structured facts)
