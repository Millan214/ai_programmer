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

_(fill in as you go)_
