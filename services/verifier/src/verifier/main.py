"""Uvicorn entry point. ``uvicorn verifier.main:app`` serves the Verifier's FastAPI app."""

import uvicorn

from verifier.service import app

__all__ = ["app"]


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8001)
