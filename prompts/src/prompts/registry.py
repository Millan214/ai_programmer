"""Versioned prompt registry. See docs/tasks/phase-0/02-prompts-package.md."""


def get_prompt(agent: str, name: str) -> str:
    """Load the active version of a prompt for `agent`. Stub — no versions registered yet."""
    raise NotImplementedError
