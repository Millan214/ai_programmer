# Task 05 — Verifier service v0

## Context

The Verifier is a deterministic subsystem (not an agent) that runs build/typecheck/lint/tests and returns structured facts. See ADR-0006. Phase 0 scope covers TypeScript projects using pnpm — the demo repo. Extension to Python and other stacks is Phase 1.

## Prereqs

- Scaffold complete.

## Scope

Files to create in `services/verifier/`:

- `src/verifier/models.py` — Pydantic result models matching ADR-0006's structured output:
  - `class VerifierResult(BaseModel): build: BuildResult; typecheck: TypecheckResult; tests: TestResult; lint: LintResult`
  - Each sub-model has `status: Literal["pass", "fail", "skip"]` plus specifics (errors list for typecheck, failures list for tests, etc.).
- `src/verifier/runners/pnpm.py`:
  - `async def build(cwd: Path) -> BuildResult` — shells `pnpm build`. Parses exit code and stderr for errors.
  - `async def typecheck(cwd: Path) -> TypecheckResult` — shells `pnpm exec tsc --noEmit`. Parses `file(line,col): error TSxxxx: message` output.
  - `async def test(cwd: Path) -> TestResult` — shells `pnpm test --reporter=json` (assumes vitest). Parses JSON output for pass/fail counts and failures.
  - `async def lint(cwd: Path) -> LintResult` — shells `pnpm exec biome check`. Parses output.
- `src/verifier/service.py`:
  - `async def verify(cwd: Path) -> VerifierResult` — runs all four concurrently with `asyncio.gather`, returns combined result.
  - FastAPI app with one endpoint: `POST /verify` with body `{"worktree_path": "/abs/path"}`, returns `VerifierResult`.
- `src/verifier/main.py` — uvicorn entrypoint.
- `tests/fixtures/passing-project/` — a tiny TS project (package.json + tsconfig + src + vitest config) that builds/tests/typechecks/lints clean.
- `tests/fixtures/failing-project/` — same shape but with a type error and a failing test.
- `tests/test_runners.py`:
  - Passing project: all four runners return `status="pass"`.
  - Failing project: typecheck fails with the specific error, tests fail with the specific failure.
- `tests/test_service.py`:
  - HTTP endpoint returns 200 with a valid `VerifierResult`.
  - Nonexistent path returns 400.

Update `services/orchestrator/src/orchestrator/graph.py` to call the real Verifier via HTTP in the verify node (replace fake from task 03).

## Success criteria

```bash
cd services/verifier
pytest -q                              # exit 0

# Run the service
uvicorn verifier.main:app --port 8001 &
curl -X POST http://localhost:8001/verify \
  -H 'content-type: application/json' \
  -d '{"worktree_path": "/abs/path/to/tests/fixtures/passing-project"}'
# Returns valid VerifierResult with all status="pass"
```

## Non-goals

- **No security scanners.** Semgrep, Trivy, gitleaks land in Phase 2.
- **No coverage tracking.** Phase 1.
- **No Python / Go / Rust runners.** Phase 1.
- **No Docker isolation of the runner.** Task 06 handles sandbox integration.
- **No caching.** Every call runs everything. Content-hash caching lands in Phase 1.
- **No retry.** If a runner errors mid-execution, propagate. No silent retries.

## Effort

~3 hours.

## Notes

Several deviations from the spec's literal tool invocations, all found by running the
real toolchain against the fixtures before writing parsers (not guessed):

- **`pnpm test --reporter=json` doesn't work.** Bare, pnpm parses the flag as its own
  unrecognized option and drops it silently. The documented fix (a `--` separator) was
  itself unreliable — it worked from an interactive shell but forwarded the `--` itself
  as a literal arg to vitest when spawned via `create_subprocess_shell`. Runner uses
  `pnpm exec vitest run --reporter=json` instead, same as the lint/typecheck runners.
- **`tsc` writes `file(line,col): error TSxxxx: ...` to stdout, not stderr** — for both
  `--noEmit` and a real build. `build()`/`typecheck()` parse combined stdout+stderr.
- **Windows: `pnpm`/`biome`/`tsc` resolve to `.cmd` shims**, which
  `asyncio.create_subprocess_exec` can't launch directly (`CreateProcess` needs a real
  PE executable). `runners/pnpm.py::_run` falls back to `create_subprocess_shell` on
  `win32`.
- **`biome check` bundles formatter checks in with linting** by default (and defaults to
  tab indentation), which would fail a fixture on style alone. Fixture `biome.json`
  disables `formatter`/`organizeImports` so `check` == pure linting, matching ADR-0006's
  "Lint" facet. `--reporter=json` is stable enough in practice despite biome's own
  "unstable/experimental" stderr warning.
- **Fixture installs needed walling off from the repo's root pnpm workspace.** Even
  though `pnpm-workspace.yaml` at the repo root only globs `apps/*`, running `pnpm
  install` inside a fixture still got silently absorbed into that workspace (no error,
  no local `node_modules` — a real footgun). Each fixture has its own
  `pnpm-workspace.yaml` (empty `packages:`, implicitly walling it off) with `allowBuilds`
  set for `@biomejs/biome`/`esbuild` so pnpm's build-script-approval prompt doesn't turn
  into a nonzero exit code in non-interactive installs.
- **Parsers use small internal Pydantic models** (`_VitestReport`, `_BiomeReport`, etc.)
  instead of manual `dict[str, object].get(...)` chains — pyright strict can't narrow
  `object` far enough for the manual version without a wall of `isinstance` checks.

**Orchestrator wiring:** `graph.py`'s `_verify_node` needed no changes — it already
calls `self._verifier.verify(edits)` through the protocol. The real wiring is
`orchestrator/verifier_client.py` (`VerifierHttpClient`, flattens `VerifierResult` to
the `{"build": "pass"/"fail", ...}` shape `_verify_passed` already routes on) plus a
`VERIFIER_URL` env-var gate in `main.py`, mirroring card 04's `ANTHROPIC_API_KEY` gate
for the Planner. It's real and tested (mocked transport) but functionally dormant until
card 08's Developer agent starts putting a `worktree_path` in `edits` — there's no real
checkout to verify yet without it, and the client raises clearly rather than faking a
result if that key is missing.
