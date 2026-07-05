.PHONY: install check test test-integration test-e2e up down

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

test-e2e:
	uv run pytest -m e2e

up:
	docker compose up -d

down:
	docker compose down
