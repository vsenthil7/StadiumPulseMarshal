"""Observability endpoints: Prometheus metrics, liveness and readiness."""
from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import PlainTextResponse

from app.core.context import AppContext
from app.observability.metrics import get_metrics

router = APIRouter(prefix="/api/v1", tags=["observability"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(get_metrics().render(), media_type="text/plain")


@router.get("/ready")
async def ready(request: Request) -> dict:
    """Readiness: report the state of each dependency subsystem."""
    ctx = _ctx(request)
    checks = {
        "observability_client": ctx.client.mode,
        "agent": ctx.agent.backend,
        "persistence": "sql" if ctx.repos.database is not None else "memory",
    }
    return {"status": "ready", "checks": checks}
