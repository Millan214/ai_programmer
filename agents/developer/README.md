# platform-developer

Developer agent: the ReAct loop that edits code in the sandbox (card 08).

- `agent.py` — the loop: one tool call per model turn, verifier auto-run after every
  edit, exits on green verifier / token budget / stuck detection / iteration cap.
  Every iteration persists an `agent_turn` row. Model: `DEVELOPER_MODEL`
  (default `claude-sonnet-4-6` — balanced tier for many-call tool-use loops).
- `tools.py` — the tool surface, each wrapping one platform service over HTTP:
  Context Provider (`retrieve`), sandbox exec (`read_file`/`edit_file`), Verifier
  (`run_verifier`).
- `adapter.py` — adapts to the orchestrator's dict protocol and owns the sandbox
  lifecycle around one build.
- `sandbox_client.py` — spawn/destroy against the sandbox controller.

Env: `DEVELOPER_MODEL`, `DEVELOPER_MAX_ITERATIONS` (default 15),
`MAX_DEVELOPER_TOKENS_PER_TASK` (default 200000), plus the service URLs
(`SANDBOX_URL`, `VERIFIER_URL`, `CONTEXT_PROVIDER_URL`) wired in `orchestrator.main`.
