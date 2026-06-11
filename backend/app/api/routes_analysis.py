"""Routes for SLO trends, postmortems, incident search and bulk operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.auth import require_permission
from app.api.schemas_ext import IncidentListResponse, Page
from app.core.context import AppContext
from app.core.errors import NotFoundError
from app.models.enums import Severity
from app.models.incident import IncidentState
from app.rbac.policy import Permission
from app.services.postmortem import Postmortem, generate_postmortem
from app.services.slo_history import SLOTrend

router = APIRouter(prefix="/api/v1", tags=["analysis"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


class SLOTrendResponse(BaseModel):
    trends: list[SLOTrend]


class PostmortemResponse(BaseModel):
    postmortem: Postmortem


class BulkTransitionRequest(BaseModel):
    incident_ids: list[str]
    target: IncidentState
    actor: str = "sre-operator"


class BulkTransitionResponse(BaseModel):
    succeeded: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)


@router.get("/slo/trends", response_model=SLOTrendResponse, tags=["slo"])
async def slo_trends(
    request: Request,
    _p=Depends(require_permission(Permission.SLO_READ)),
) -> SLOTrendResponse:
    ctx = _ctx(request)
    # Ensure at least one sample exists.
    await ctx.evaluate_slos()
    return SLOTrendResponse(trends=ctx.slo_history.all_trends())


@router.get(
    "/incidents/{incident_id}/postmortem",
    response_model=PostmortemResponse,
    tags=["incidents"],
)
async def incident_postmortem(
    request: Request,
    incident_id: str,
    _p=Depends(require_permission(Permission.INCIDENT_READ)),
) -> PostmortemResponse:
    ctx = _ctx(request)
    incident = await ctx.incidents.get(incident_id)
    if incident is None:
        raise NotFoundError("Incident not found")
    return PostmortemResponse(postmortem=generate_postmortem(incident))


@router.get(
    "/incidents-search", response_model=IncidentListResponse, tags=["incidents"]
)
async def search_incidents(
    request: Request,
    state: IncidentState | None = None,
    severity: Severity | None = None,
    text: str | None = None,
    venue_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _p=Depends(require_permission(Permission.INCIDENT_READ)),
) -> IncidentListResponse:
    ctx = _ctx(request)
    results, total = await ctx.incidents.search(
        state=state, severity=severity, text=text, venue_id=venue_id,
        offset=offset, limit=limit,
    )
    return IncidentListResponse(
        incidents=results, page=Page(total=total, offset=offset, limit=limit)
    )


@router.post(
    "/incidents-bulk/transition",
    response_model=BulkTransitionResponse,
    tags=["incidents"],
)
async def bulk_transition(
    request: Request,
    body: BulkTransitionRequest,
    _p=Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> BulkTransitionResponse:
    ctx = _ctx(request)
    result = await ctx.incidents.bulk_transition(
        body.incident_ids, body.target, actor=body.actor
    )
    return BulkTransitionResponse(**result)
