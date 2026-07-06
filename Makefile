.PHONY: install check test test-integration test-e2e up down demo-repo

install:
	uv sync --all-packages
	pnpm install

check:
	uv run ruff check .
	uv run pyright
	pnpm run check

test:
	uv run pytest -m "not integration"
	pnpm -r test

test-integration:
	uv run pytest -m integration

# Full loop against real services. Needs `make up`, ANTHROPIC_API_KEY, and Docker.
# The tests live under tests/e2e (outside the unit testpaths) and self-skip if the
# prereqs are absent; each test bounds its own runtime by polling with a 5-minute cap.
test-e2e:
	uv run pytest tests/e2e -v

up:
	docker compose up -d

down:
	docker compose down

# One-time: turn target-repos/demo-lib into its own git repo (sandbox worktrees spawn
# from it) and install its toolchain. Safe to re-run.
demo-repo:
	cd target-repos/demo-lib && ([ -d .git ] || git init -q) && pnpm install
	cd target-repos/demo-lib && git add -A && (git diff --cached --quiet || git commit -q -m "demo-lib snapshot")
