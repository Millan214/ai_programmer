"""Unit tests for ``VerifierHttpClient`` against a mocked transport — no real Verifier
service or network needed. See ``services/verifier/tests`` for the real HTTP surface.
"""

import json
import uuid
from typing import Any

import httpx
import pytest
from orchestrator.verifier_client import VerifierClientError, VerifierHttpClient

_SESSION_ID = uuid.uuid4()

_VERIFIER_RESULT: dict[str, object] = {
    "build": {"status": "pass", "error": None},
    "typecheck": {"status": "pass", "errors": []},
    "tests": {"status": "fail", "total": 1, "passed": 0, "failed": 1, "failures": []},
    "lint": {"status": "pass", "errors": 0, "warnings": 0, "issues": []},
}


def _mock_async_client(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    real_async_client = httpx.AsyncClient

    def patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = handler
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


@pytest.mark.asyncio
async def test_verify_flattens_result_to_status_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/verify"
        # The session rides along so the Verifier can persist a ``verifier_run`` row.
        assert json.loads(request.content)["session_id"] == str(_SESSION_ID)
        return httpx.Response(200, json=_VERIFIER_RESULT)

    _mock_async_client(monkeypatch, httpx.MockTransport(handler))

    client = VerifierHttpClient("http://verifier.invalid:8001")
    facts = await client.verify({"worktree_path": "/repo/worktree"}, _SESSION_ID)

    assert facts == {"build": "pass", "typecheck": "pass", "tests": "fail", "lint": "pass"}


@pytest.mark.asyncio
async def test_verify_raises_without_worktree_path() -> None:
    client = VerifierHttpClient("http://verifier.invalid:8001")
    with pytest.raises(VerifierClientError):
        await client.verify({"diff": "stub", "files": []}, _SESSION_ID)


@pytest.mark.asyncio
async def test_verify_propagates_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    _mock_async_client(monkeypatch, httpx.MockTransport(handler))

    client = VerifierHttpClient("http://verifier.invalid:8001")
    with pytest.raises(httpx.HTTPStatusError):
        await client.verify({"worktree_path": "/repo/worktree"}, _SESSION_ID)
