# AI Coding Platform

A multi-agent system that plans, implements, reviews, tests, documents, and ships software
changes as pull requests. See [`CLAUDE.md`](CLAUDE.md) for the full architecture and conventions.

Currently in **Phase 0**: an end-to-end skeleton that completes a trivial task on one demo
target repo. Work queue: [`docs/tasks/phase-0/`](docs/tasks/phase-0/). Decisions:
[`docs/adr/`](docs/adr/).

## Getting started

```bash
cp .env.example .env   # fill in secrets
make install
make check
make test
make up                # postgres, jaeger, minio
```
