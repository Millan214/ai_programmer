# Task 02 — Versioned prompt registry

## Context

Prompts are versioned files in source control (`CLAUDE.md` non-negotiable #3). Every prompt served is recorded on the `agent_turn` row that used it. This card builds the registry that loads, pins, and serves prompts to agents.

## Prereqs

- Scaffold complete.

## Scope

Files to create in `prompts/`:

- `src/prompts/versions/planner/plan@v1.md` — placeholder Planner prompt with `{{task_description}}` variable. Content can be a rough first draft; it evolves.
- `src/prompts/versions/developer/build@v1.md` — placeholder Developer prompt with `{{plan}}`, `{{repo_map}}` variables.
- `src/prompts/registry.py`:
  - `class PromptRef(BaseModel): agent: str; name: str; version: str`
  - `def load(ref: PromptRef) -> str` — reads file, returns raw text. Raises on missing.
  - `def render(ref: PromptRef, **vars) -> str` — renders variables. Use `str.format_map()` with a safe dict, or `jinja2` if you want conditionals; either is fine, document the choice.
  - `def active_version(agent: str, name: str) -> str` — reads from a `versions.toml` config file in `prompts/`.
- `versions.toml` — pins the active version per (agent, name):
  ```toml
  [planner]
  plan = "v1"
  [developer]
  build = "v1"
  ```
- `tests/test_registry.py`:
  - Loading known prompts returns non-empty strings.
  - Loading unknown (agent, name, version) raises `PromptNotFoundError`.
  - Rendering with all required variables works; missing variables raise.
  - `active_version` reads from `versions.toml` correctly.

## Success criteria

```bash
cd prompts
pytest -q                              # exit 0
python -c "from prompts.registry import load, PromptRef; \
  print(load(PromptRef(agent='planner', name='plan', version='v1'))[:100])"
# Prints first 100 chars of the planner prompt.
```

`make check && make test` from repo root: green.

## Non-goals

- **No prompt regression harness.** That's Phase 1.
- **No DSPy or automated optimization.** Phase 3+.
- **No hot-reloading.** Prompts load once per process; restart to pick up changes.
- **No prompt content review.** The v1 prompts are placeholders. Getting the loader right matters; getting the words right is a later iteration.
- **No template inheritance or partials.** Keep it flat.

## Effort

~2 hours.

## Notes

- **Rendering uses `str.format_map()`, not jinja2.** Placeholders are flat vars
  (`{task_description}`, `{plan}`, `{repo_map}`) — no conditionals/loops needed yet, and it avoids
  a template-engine dependency for Phase 0. Missing variables raise `PromptRenderError` (wraps the
  underlying `KeyError`). Note the card text used `{{double_brace}}` notation; since we picked
  `format_map` the actual placeholder syntax in the `.md` files is single-brace `{var}`.
- **`versions.toml` lives at `prompts/` (package root, sibling to `src/`)**, not inside
  `src/prompts/`. `registry.py` locates it via `Path(__file__).resolve().parents[1]`.
- **Prompt-authoring convention that follows from `format_map`:** literal `{`/`}` in prompt
  content must be doubled (`{{`/`}}`). The planner prompt's JSON output skeleton does this; an
  unescaped brace shows up as `PromptRenderError` (or worse, a silently mangled prompt) at render
  time. `tests/test_registry.py` has structural pins that render both v1 prompts end-to-end, so a
  bad escape fails CI. Values substituted *into* slots are never re-formatted, so task
  descriptions/plans containing braces or JSON are safe.
- v1 content is real, not placeholder: planner pins the JSON contract that card 04's `Plan` model
  parses (`subtasks[].title/description/acceptance`, `risks`, `estimated_files`); developer names
  card 08's exact tool surface (`retrieve`, `read_file`, `edit_file`, `run_verifier`) and encodes
  ADR-0006 (verifier facts only) plus the stuck-loop rule. If cards 04/08 change either contract,
  bump to v2 — the structural tests will point at the mismatch.
- **Real pytest gotcha, cost real debugging time:** this workspace member's directory is named
  `prompts/`, identical to the installed package's import name (`prompts`). Pytest's
  `--import-mode=importlib`, when it can't resolve a test file's module name via a real
  `__init__.py` chain, falls back to synthesizing a dotted name *relative to rootdir*
  (`prompts.tests.test_registry`) and injects a bogus namespace module into `sys.modules["prompts"]`
  pointing at the bare `prompts/` directory — which shadows the real editable-installed package and
  breaks `from prompts.registry import ...` inside the test file itself. Every other workspace
  member dodges this by accident (their directory name, e.g. `db`, doesn't match their import name,
  e.g. `platform_db`). **Fix:** added an empty `prompts/tests/__init__.py`, which gives pytest a
  real `__init__.py` chain to resolve (`tests.test_registry`) instead of hitting the buggy rootdir
  fallback. No other test directory in the repo has an `__init__.py`; don't add one there
  reflexively — only `prompts/tests/` needs it, precisely because of the name collision above. If a
  future package's workspace folder name ever matches its import name, expect the same failure.
