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
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.errors import register_exception_handlers
from app.middleware.metrics import RequestMetricsMiddleware
from app.middleware.tracing import TraceContextMiddleware

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
    # Middleware order: trace context outermost, then correlation, then metrics.
    app.add_middleware(RequestMetricsMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(TraceContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.rate_limit_enabled:
        from app.middleware.ratelimit import RateLimitMiddleware

        app.add_middleware(RateLimitMiddleware)

    if settings.csrf_enabled:
        from app.middleware.csrf import CSRFMiddleware

        app.add_middleware(CSRFMiddleware, cookie_secure=settings.cookie_secure)

    if settings.security_headers_enabled:
        from app.middleware.security_headers import SecurityHeadersMiddleware

        app.add_middleware(
            SecurityHeadersMiddleware,
            csp=settings.csp_override,
            hsts=settings.hsts_enabled,
        )

    register_exception_handlers(app)

    app.include_router(router)

    from app.api.routes_analysis import router as analysis_router
    from app.api.routes_audit import router as audit_router
    from app.api.routes_auth import oidc_router
    from app.api.routes_auth import router as auth_router
    from app.api.routes_incidents import router as incidents_router
    from app.api.routes_observability import router as obs_router
    from app.api.routes_ops import router as ops_router
    from app.api.routes_venues import router as venues_router
    from app.api.routes_webhooks import router as webhooks_router
    from app.api.routes_runbooks import router as runbooks_router
    from app.api.routes_postmortems import router as postmortems_router
    from app.api.routes_enterprise import router as enterprise_router

    app.include_router(incidents_router)
    app.include_router(ops_router)
    app.include_router(obs_router)
    app.include_router(webhooks_router)
    app.include_router(analysis_router)
    app.include_router(audit_router)
    app.include_router(auth_router)
    app.include_router(oidc_router)
    app.include_router(venues_router)
    app.include_router(runbooks_router)
    app.include_router(postmortems_router)
    app.include_router(enterprise_router)

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
