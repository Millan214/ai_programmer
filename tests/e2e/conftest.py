"""End-to-end harness (card 11): real Postgres + Jaeger via compose, the four Python
services as subprocesses, a stub retrieval backend, and demo-lib prepared as a git repo.

Skips the whole module unless the prereqs are actually present — an `ANTHROPIC_API_KEY`
(the run uses real agents) and a reachable Docker daemon. The services bind to fixed local
ports; the orchestrator runs in-process inside task-api (it isn't a server), so only four
processes start.

Platform note: this harness targets Linux/CI. On a Windows host two things break — psycopg's
async loop under uvicorn's default proactor loop, and the split between an in-container
`pnpm install` (Linux binaries) and a host-side Verifier (Windows) — so `make test-e2e` is
green on Linux (where the nightly workflow runs), not on a Windows dev box.
"""

import contextlib
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_LIB = _REPO_ROOT / "target-repos" / "demo-lib"
_SANDBOX_DOCKERFILE_DIR = _REPO_ROOT / "services" / "sandbox" / "src" / "sandbox"

# Fixed local ports for the harness.
STUB_MCP_PORT = 8009
CONTEXT_PROVIDER_PORT = 8001
VERIFIER_PORT = 8002
SANDBOX_PORT = 8003
TASK_API_PORT = 8000

TASK_API_URL = f"http://localhost:{TASK_API_PORT}"


def _docker_ok() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, check=False, timeout=15
            ).returncode
            == 0
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip the whole e2e suite (not error) when its prereqs are absent. Lives here rather
    than as a module ``pytestmark`` because a conftest ``pytestmark`` doesn't apply to
    tests in other files — this hook is scoped to items under tests/e2e and does."""
    missing: list[str] = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not _docker_ok():
        missing.append("a running Docker daemon")
    if not missing:
        return
    skip = pytest.mark.skip(reason="e2e needs: " + ", ".join(missing))
    for item in items:
        item.add_marker(skip)


def _wait_http(url: str, *, timeout_s: float = 40.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code < 500:
                return
        except httpx.HTTPError as exc:  # not up yet
            last_err = exc
        time.sleep(0.5)
    raise RuntimeError(f"service at {url} never came up: {last_err}")


def _run(cmd: list[str], *, cwd: Path | None = None, timeout_s: int = 300) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@pytest.fixture(scope="session")
def infra() -> Iterator[None]:
    """Postgres (required) + Jaeger (best-effort) via compose, migrations applied, image built."""
    _run(["docker", "compose", "up", "-d", "postgres"], cwd=_REPO_ROOT)
    # Jaeger is nice-to-have — the tests don't assert on traces, and a host may already
    # have something on the OTLP port (4317). Don't fail the smoke test over the trace
    # backend; if it can't start, tracing just goes nowhere (configure() is offline-safe).
    with contextlib.suppress(RuntimeError):
        _run(["docker", "compose", "up", "-d", "jaeger"], cwd=_REPO_ROOT, timeout_s=120)
    _wait_for_postgres()
    _run(["uv", "run", "alembic", "upgrade", "head"], cwd=_REPO_ROOT / "packages" / "db")
    _run(
        ["docker", "build", "-t", "platform-sandbox:phase0", "."],
        cwd=_SANDBOX_DOCKERFILE_DIR,
        timeout_s=600,
    )
    yield
    _run(["docker", "compose", "down"], cwd=_REPO_ROOT, timeout_s=120)


def _wait_for_postgres(timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres", "pg_isready", "-U", "platform"],
            cwd=_REPO_ROOT,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(1.0)
    raise RuntimeError("postgres never became ready")


@pytest.fixture(scope="session")
def demo_repo() -> str:
    """Ensure demo-lib is a git repo with a clean, committed tree (worktrees spawn from it)."""
    if not (_DEMO_LIB / ".git").is_dir():
        _run(["git", "init", "-q"], cwd=_DEMO_LIB)
    _run(["git", "add", "-A"], cwd=_DEMO_LIB)
    # Commit only if there's something to commit (idempotent across runs).
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=_DEMO_LIB, check=False
    )
    if staged.returncode != 0:
        _run(["git", "commit", "-q", "-m", "demo-lib snapshot"], cwd=_DEMO_LIB)
    return str(_DEMO_LIB)


def _start_service(
    module_app: str, port: int, extra_env: dict[str, str]
) -> subprocess.Popen[bytes]:
    env = {**os.environ, **extra_env}
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", module_app, "--port", str(port), "--log-level", "warning"],
        cwd=_REPO_ROOT,
        env=env,
    )
    _wait_http(f"http://localhost:{port}/openapi.json")
    return proc


@pytest.fixture(scope="session")
def services(infra: None, demo_repo: str) -> Iterator[str]:
    """Start stub-MCP + the four services; yield the task-API base URL."""
    otel = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    stub_url = f"http://localhost:{STUB_MCP_PORT}"
    procs: list[subprocess.Popen[bytes]] = []
    try:
        procs.append(
            _start_service(
                "stub_mcp:app",
                STUB_MCP_PORT,
                {"PYTHONPATH": str(Path(__file__).parent)},
            )
        )
        procs.append(
            _start_service(
                "context_provider.main:app",
                CONTEXT_PROVIDER_PORT,
                {"GRAPHIFY_MCP_URL": stub_url, "CRG_MCP_URL": stub_url,
                 "OTEL_EXPORTER_OTLP_ENDPOINT": otel},
            )
        )
        procs.append(
            _start_service(
                "verifier.service:app",
                VERIFIER_PORT,
                {"OTEL_EXPORTER_OTLP_ENDPOINT": otel},
            )
        )
        procs.append(
            _start_service(
                "sandbox.service:app",
                SANDBOX_PORT,
                {"OTEL_EXPORTER_OTLP_ENDPOINT": otel},
            )
        )
        procs.append(
            _start_service(
                "task_api.main:app",
                TASK_API_PORT,
                {
                    "SANDBOX_URL": f"http://localhost:{SANDBOX_PORT}",
                    "VERIFIER_URL": f"http://localhost:{VERIFIER_PORT}",
                    "CONTEXT_PROVIDER_URL": f"http://localhost:{CONTEXT_PROVIDER_PORT}",
                    "OTEL_EXPORTER_OTLP_ENDPOINT": otel,
                },
            )
        )
        yield TASK_API_URL
    finally:
        for proc in reversed(procs):
            proc.terminate()
        for proc in reversed(procs):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
