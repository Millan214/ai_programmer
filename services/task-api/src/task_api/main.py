"""Task API FastAPI app. Run with ``uvicorn task_api.main:app --port 8000``."""

from fastapi import FastAPI
from platform_telemetry import lifespan_for

from task_api.routes import router

app = FastAPI(title="Task API", lifespan=lifespan_for("task-api"))
app.include_router(router)


def run() -> None:
    """Console entry point — serve the API with uvicorn."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
