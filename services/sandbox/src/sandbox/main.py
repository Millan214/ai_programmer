"""Uvicorn entry point. ``uvicorn sandbox.main:app`` serves the sandbox controller's
FastAPI app."""

import uvicorn

from sandbox.service import app

__all__ = ["app"]


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8002)
