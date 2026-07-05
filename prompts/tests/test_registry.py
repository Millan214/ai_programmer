import pytest
from prompts.registry import (
    PromptNotFoundError,
    PromptRef,
    PromptRenderError,
    active_version,
    load,
    render,
)


def test_load_known_prompt_returns_non_empty_string():
    text = load(PromptRef(agent="planner", name="plan", version="v1"))
    assert text.strip()


def test_load_unknown_agent_raises():
    with pytest.raises(PromptNotFoundError):
        load(PromptRef(agent="nonexistent", name="plan", version="v1"))


def test_load_unknown_name_raises():
    with pytest.raises(PromptNotFoundError):
        load(PromptRef(agent="planner", name="nonexistent", version="v1"))


def test_load_unknown_version_raises():
    with pytest.raises(PromptNotFoundError):
        load(PromptRef(agent="planner", name="plan", version="v99"))


def test_render_with_required_variables():
    text = render(PromptRef(agent="planner", name="plan", version="v1"), task_description="do X")
    assert "do X" in text


def test_render_missing_variable_raises():
    with pytest.raises(PromptRenderError):
        render(PromptRef(agent="planner", name="plan", version="v1"))


def test_active_version_reads_versions_toml():
    assert active_version("planner", "plan") == "v1"
    assert active_version("developer", "build") == "v1"


def test_active_version_unknown_raises():
    with pytest.raises(PromptNotFoundError):
        active_version("planner", "nonexistent")


# Structural pins on prompt content (CLAUDE.md "how to add a prompt version").
# Pin only what agent code depends on: placeholder slots, output contract, tool names.


def test_planner_plan_v1_structure():
    raw = load(PromptRef(agent="planner", name="plan", version="v1"))
    assert "{task_description}" in raw

    rendered = render(
        PromptRef(agent="planner", name="plan", version="v1"), task_description="do X"
    )
    # The JSON output skeleton must survive rendering with real (un-doubled) braces,
    # and must name the fields Plan/Subtask (card 04) will parse.
    for field in ('"subtasks"', '"title"', '"description"', '"acceptance"',
                  '"risks"', '"estimated_files"'):
        assert field in rendered
    assert "{{" not in rendered and "}}" not in rendered


def test_developer_build_v1_structure():
    raw = load(PromptRef(agent="developer", name="build", version="v1"))
    assert "{plan}" in raw
    assert "{repo_map}" in raw
    # Tool surface from card 08 — the prompt must name exactly these tools.
    for tool in ("retrieve", "read_file", "edit_file", "run_verifier"):
        assert tool in raw

    rendered = render(
        PromptRef(agent="developer", name="build", version="v1"),
        plan='{"subtasks": []}',
        repo_map="src/\n  math.ts",
    )
    assert '{"subtasks": []}' in rendered
    assert "math.ts" in rendered
