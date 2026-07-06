# demo-lib

The Phase 0 demo target repo — the tiny TypeScript library the platform's agents
operate on. Mirrors the Verifier's `passing-project` fixture (same pinned toolchain:
tsc, vitest, biome) so every check is known to pass and parse cleanly.

This directory's *source* is committed to the platform repo, but the sandbox needs it
to be its own git repository (worktrees are spawned from it). One-time setup from the
platform root:

```bash
make demo-repo
```

That runs `git init` + `pnpm install` + an initial commit inside this directory (the
nested `.git` is invisible to the platform repo). Point the platform at it with
`DEMO_REPO_PATH=<abs path to this dir>`.

A fresh `git worktree add` from this repo carries only tracked files — no
`node_modules` — so the sandbox installs dependencies at spawn time via its
`setup_commands` (default `pnpm install --frozen-lockfile`, from the developer
adapter's `SANDBOX_SETUP_COMMANDS`). That's why the committed `pnpm-lock.yaml` matters:
the frozen install reproduces exactly what's pinned here.
