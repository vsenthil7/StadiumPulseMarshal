"""Optionally mount the built frontend so the API and UI share one origin.

If ``frontend/dist`` exists (after ``npm run build``), it is served at ``/``.
This is used for E2E tests and single-container deployment. When absent (pure
API dev), this is a no-op.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, HTMLResponse

from app.core.logging import get_logger

log = get_logger(__name__)

_TAG_RE = re.compile(r"<(script|style|link)\b")


def _inject_nonce(html: str, nonce: str) -> str:
    """Add ``nonce="..."`` to script/style/link tags so a nonce-based CSP can
    whitelist them without 'unsafe-inline' for scripts."""
    return _TAG_RE.sub(lambda m: f'<{m.group(1)} nonce="{nonce}"', html)


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

    def _render_index(request: Request) -> HTMLResponse:
        nonce = getattr(request.state, "csp_nonce", None)
        html = index.read_text(encoding="utf-8")
        if nonce:
            html = _inject_nonce(html, nonce)
        return HTMLResponse(html)

    @app.get("/", include_in_schema=False)
    async def _index(request: Request) -> HTMLResponse:  # pragma: no cover
        return _render_index(request)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str, request: Request):  # pragma: no cover
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return _render_index(request)

    log.info("Mounted frontend from %s", dist)
    return True
