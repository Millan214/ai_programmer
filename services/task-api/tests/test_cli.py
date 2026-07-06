"""CLI tests — Click's ``CliRunner`` against a mocked API via ``httpx.MockTransport``."""

import uuid
from collections.abc import Callable

import httpx
import pytest
from click.testing import CliRunner
from task_api import cli

_TASK_ID = str(uuid.uuid4())

_Handler = Callable[[httpx.Request], httpx.Response]


def _install_mock(monkeypatch: pytest.MonkeyPatch, handler: _Handler) -> None:
    def fake_client() -> httpx.Client:
        return httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))

    monkeypatch.setattr(cli, "_client", fake_client)


def test_submit_prints_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks"
        return httpx.Response(200, json={"task_id": _TASK_ID, "status": "queued"})

    _install_mock(monkeypatch, handler)

    result = CliRunner().invoke(
        cli.main,
        ["submit", "--repo", "demo-lib", "--title", "t", "--description", "d"],
    )

    assert result.exit_code == 0, result.output
    assert f"task_id: {_TASK_ID}" in result.output


def test_status_prints_phase_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/tasks/{_TASK_ID}"
        return httpx.Response(
            200,
            json={
                "task_id": _TASK_ID,
                "repo": "demo-lib",
                "title": "t",
                "status": "completed",
                "phase": "ship",
                "verifier": {"build": "pass", "typecheck": "pass", "tests": "pass", "lint": "pass"},
                "created_at": "2026-07-06T00:00:00Z",
            },
        )

    _install_mock(monkeypatch, handler)

    result = CliRunner().invoke(cli.main, ["status", _TASK_ID])

    assert result.exit_code == 0, result.output
    assert "status: completed" in result.output
    assert "phase: ship" in result.output
    assert "build=pass" in result.output


def test_status_reports_missing_task(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    _install_mock(monkeypatch, handler)

    result = CliRunner().invoke(cli.main, ["status", _TASK_ID])

    assert result.exit_code != 0
    assert "not found" in result.output


def test_list_prints_table(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks"
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "task_id": _TASK_ID,
                        "repo": "demo-lib",
                        "title": "add helper",
                        "status": "queued",
                        "created_at": "2026-07-06T00:00:00Z",
                    }
                ],
                "limit": 5,
                "offset": 0,
            },
        )

    _install_mock(monkeypatch, handler)

    result = CliRunner().invoke(cli.main, ["list", "--limit", "5"])

    assert result.exit_code == 0, result.output
    assert _TASK_ID in result.output
    assert "add helper" in result.output
