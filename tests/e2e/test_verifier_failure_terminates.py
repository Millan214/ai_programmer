"""The failure path: a task whose change makes the Verifier red must end ``failed_verify``
and never reach ship. The failing test is spelled out literally so the outcome is
deterministic — no reliance on the model choosing to produce a failure.
"""

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _db import agent_turns, engine, session_ids  # noqa: E402

_POLL_INTERVAL_S = 5
_POLL_TIMEOUT_S = 300
_TERMINAL = {"completed", "failed_verify"}

_FAILING_TASK = {
    "repo": None,
    "title": "add a deliberately failing test",
    "description": (
        "Create the file src/always_fails.test.ts containing exactly this and nothing else:\n"
        "import { test, expect } from 'vitest';\n"
        "test('this always fails', () => { expect(1).toBe(2); });\n"
        "Do not modify any other file."
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


def test_failing_verifier_terminates_without_shipping(services: str, demo_repo: str) -> None:
    base_url = services

    resp = httpx.post(
        f"{base_url}/tasks", json={**_FAILING_TASK, "repo": demo_repo}, timeout=30
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["task_id"]

    status = _poll_until_terminal(base_url, task_id)
    assert status == "failed_verify", f"task ended {status}, expected failed_verify"

    # No ship turn: the ship node writes an agent with the fake PR ref only when it runs.
    eng = engine()
    sids = session_ids(eng, task_id)
    turns = agent_turns(eng, sids)
    assert not any(t.agent == "shipper" for t in turns), "ship ran despite a red verifier"
