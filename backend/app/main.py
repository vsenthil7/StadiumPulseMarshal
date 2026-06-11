"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.context import AppContext
from app.core.logging import get_logger

log = get_logger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.ctx = AppContext(settings)
    await app.state.ctx.startup()
    log.info(
        "%s v%s started (data_source=%s, agent=%s)",
        settings.app_name,
        settings.app_version,
        settings.data_source,
        app.state.ctx.agent.backend,
    )
    try:
        yield
    finally:
        await app.state.ctx.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AIOps matchday operations agent (Dynatrace MCP + Gemini).",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    from app.api.routes_incidents import router as incidents_router
    from app.api.routes_ops import router as ops_router

    app.include_router(incidents_router)
    app.include_router(ops_router)

    @app.websocket("/api/v1/stream")
    async def stream(ws: WebSocket) -> None:
        """Push the live open-problem feed every few seconds."""
        await ws.accept()
        ctx: AppContext = ws.app.state.ctx
        try:
            while True:
                problems = await ctx.client.list_problems(open_only=True)
                await ws.send_json(
                    {
                        "type": "problem_feed",
                        "count": len(problems),
                        "problems": [
                            {
                                "id": p.id,
                                "title": p.title,
                                "severity": p.severity.value,
                                "phase": (
                                    p.matchday_phase.value
                                    if p.matchday_phase
                                    else None
                                ),
                            }
                            for p in problems
                        ],
                    }
                )
                await asyncio.sleep(5)
        except WebSocketDisconnect:  # pragma: no cover - network event
            log.info("stream client disconnected")

    from app.core.static import mount_frontend

    mount_frontend(app)
    return app


app = create_app()
