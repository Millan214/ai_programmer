"""Unit tests for the developer adapter's sandbox-setup resolution."""

import pytest
from developer.adapter import DEFAULT_SETUP_COMMANDS, resolve_setup_commands
from developer.models import DeveloperError


def test_default_setup_installs_with_frozen_lockfile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SANDBOX_SETUP_COMMANDS", raising=False)
    assert resolve_setup_commands() == DEFAULT_SETUP_COMMANDS
    assert resolve_setup_commands() == [["pnpm", "install", "--frozen-lockfile"]]


def test_env_override_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_SETUP_COMMANDS", '[["npm", "ci"], ["npm", "run", "prepare"]]')
    assert resolve_setup_commands() == [["npm", "ci"], ["npm", "run", "prepare"]]


def test_empty_list_disables_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_SETUP_COMMANDS", "[]")
    assert resolve_setup_commands() == []


def test_malformed_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_SETUP_COMMANDS", "not json")
    with pytest.raises(DeveloperError, match="not valid JSON"):
        resolve_setup_commands()


def test_wrong_shape_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_SETUP_COMMANDS", '["pnpm install"]')
    with pytest.raises(DeveloperError, match="list of string lists"):
        resolve_setup_commands()
