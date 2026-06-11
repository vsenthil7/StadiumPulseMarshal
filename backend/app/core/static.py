"""Optionally mount the built frontend so the API and UI share one origin.

If ``frontend/dist`` exists (after ``npm run build``), it is served at ``/``.
This is used for E2E tests and single-container deployment. When absent (pure
API dev), this is a no-op.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app.core.logging import get_logger

log = get_logger(__name__)


def mount_frontend(app: FastAPI) -> bool:
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if not dist.is_dir():
        log.info("frontend/dist not found; serving API only")
        return False

    index = dist / "index.html"
    app.mount(
        "/assets",
        StaticFiles(directory=dist / "assets"),
        name="assets",
    )

    @app.get("/", include_in_schema=False)
    async def _index() -> FileResponse:  # pragma: no cover - thin wrapper
        return FileResponse(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str) -> FileResponse:  # pragma: no cover
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    log.info("Mounted frontend from %s", dist)
    return True
