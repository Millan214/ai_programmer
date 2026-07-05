"""Versioned prompt registry. See docs/tasks/phase-0/02-prompts-package.md.

Rendering uses ``str.format_map`` (not jinja2): the placeholder prompts only need flat
variable substitution, no conditionals or loops, and it avoids adding a template-engine
dependency for Phase 0. Missing variables raise (caught ``KeyError``, re-raised below)
instead of silently rendering empty — a prompt with an unfilled slot should never reach
an agent unnoticed.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel

_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROMPTS_ROOT = _PACKAGE_ROOT.parents[1]  # prompts/ (package root, holds versions.toml)
_VERSIONS_DIR = _PACKAGE_ROOT / "versions"


class PromptRef(BaseModel):
    agent: str
    name: str
    version: str


class PromptNotFoundError(Exception):
    pass


class PromptRenderError(Exception):
    pass


def _prompt_path(ref: PromptRef) -> Path:
    return _VERSIONS_DIR / ref.agent / f"{ref.name}@{ref.version}.md"


def load(ref: PromptRef) -> str:
    path = _prompt_path(ref)
    if not path.is_file():
        raise PromptNotFoundError(f"no prompt file for {ref.agent}/{ref.name}@{ref.version}")
    return path.read_text(encoding="utf-8")


def render(ref: PromptRef, **vars: object) -> str:
    template = load(ref)
    try:
        return template.format_map(vars)
    except KeyError as exc:
        raise PromptRenderError(
            f"missing variable {exc} rendering {ref.agent}/{ref.name}@{ref.version}"
        ) from exc


def active_version(agent: str, name: str) -> str:
    config_path = _PROMPTS_ROOT / "versions.toml"
    with config_path.open("rb") as f:
        config = tomllib.load(f)
    try:
        return config[agent][name]
    except KeyError as exc:
        raise PromptNotFoundError(f"no active version pinned for {agent}/{name}") from exc


def get_prompt(agent: str, name: str) -> str:
    """Load the currently active version of a prompt for `agent`/`name`."""
    version = active_version(agent, name)
    return load(PromptRef(agent=agent, name=name, version=version))
