"""The Phase 0 exit criterion, executable: submit a well-scoped task, the real agents run
it against demo-lib, the Verifier passes, and Postgres holds an auditable trail.
"""

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _db import agent_turns, engine, latest_verifier_run, session_ids  # noqa: E402

_POLL_INTERVAL_S = 5
_POLL_TIMEOUT_S = 300
_TERMINAL = {"completed", "failed_verify"}

_TASK = {
    "repo": None,  # filled with the demo-lib absolute path in the test
    "title": "add hasPermission helper",
    "description": (
        "Add `export function hasPermission(user: string, action: string): boolean` to "
        "src/perms.ts. It returns true only when action === 'read', false otherwise. "
        "Add src/perms.test.ts with a vitest test asserting hasPermission('u', 'read') is "
        "true and hasPermission('u', 'write') is false. Change nothing else."
    ),
}


def _poll_until_terminal(base_url: str, task_id: str) -> str:
    deadline = time.monotonic() + _POLL_TIMEOUT_S
    status = "unknown"
    while time.monotonic() < deadline:
        resp = httpx.get(f"{base_url}/tasks/{task_id}", timeout=10)
        resp.raise_for_status()
        status = resp.json()["status"]
        if status in _TERMINAL:
            return status
        time.sleep(_POLL_INTERVAL_S)
    raise AssertionError(
        f"task {task_id} did not finish within {_POLL_TIMEOUT_S}s (last: {status})"
    )


def test_hello_world_task_completes_and_is_auditable(services: str, demo_repo: str) -> None:
    base_url = services

    resp = httpx.post(f"{base_url}/tasks", json={**_TASK, "repo": demo_repo}, timeout=30)
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["task_id"]

    status = _poll_until_terminal(base_url, task_id)
    assert status == "completed", f"task ended {status}, not completed"

    eng = engine()
    sids = session_ids(eng, task_id)
    assert sids, "no task_session row for the task"

    turns = agent_turns(eng, sids)
    planner = [t for t in turns if t.agent == "planner"]
    developer = [t for t in turns if t.agent == "developer"]
    assert len(planner) >= 1, "expected a planner agent_turn"
    assert len(developer) >= 1, "expected at least one developer agent_turn"

    vrun = latest_verifier_run(eng, sids)
    assert vrun is not None, "no verifier_run row"
    assert vrun["build"]["status"] == "pass"  # type: ignore[index]
    assert vrun["tests"]["status"] == "pass"  # type: ignore[index]

    total_cost = sum((t.cost_usd or 0) for t in turns)
    assert total_cost < 2, f"run cost ${total_cost}, over the $2 Phase 0 cap"

    # The Developer persists its final diff on a turn's output_ref (card 11); the produced
    # change should touch the helper file and a test file.
    diffs = [t.output_ref for t in developer if t.output_ref]
    assert diffs, "developer never persisted a diff"
    diff = diffs[-1]
    assert "perms.ts" in diff, f"diff didn't touch src/perms.ts:\n{diff[:2000]}"
    assert "perms.test.ts" in diff or "test" in diff.lower(), "diff has no test file"
