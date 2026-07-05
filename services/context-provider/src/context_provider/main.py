"""Uvicorn entry point. ``uvicorn context_provider.main:app`` serves the Context
Provider."""

import uvicorn

from context_provider.service import app

__all__ = ["app"]


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8003)
