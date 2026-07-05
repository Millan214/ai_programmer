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

_(fill in as you go)_
