"""Incident lifecycle API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.api.auth import require_permission, require_venue_access
from app.rbac.policy import Permission, Principal
from app.api.schemas_ext import (
    AssignRequest,
    CreateIncidentRequest,
    IncidentListResponse,
    IncidentResponse,
    NoteRequest,
    Page,
    TransitionRequest,
)
from app.core.context import AppContext
from app.services.incident_service import IncidentError, StaleVersionError

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def _authorize_incident(
    request: Request, incident_id: str, principal: Principal
):
    """Load an incident or 404, then enforce the principal's venue scope on it.

    Prevents acting on another venue's incident by id — defence at the entity
    level, not just on the list filter.
    """
    ctx = _ctx(request)
    incident = await ctx.incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    require_venue_access(principal, incident.venue_id)
    return incident


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    request: Request,
    open_only: bool = False,
    venue_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> IncidentListResponse:
    ctx = _ctx(request)
    # If a venue filter is supplied, the caller must be scoped to it.
    if venue_id is not None:
        require_venue_access(principal, venue_id)
    incidents = await ctx.incidents.list(
        open_only=open_only, venue_id=venue_id, offset=offset, limit=limit
    )
    total = await ctx.incidents.count(open_only=open_only, venue_id=venue_id)
    return IncidentListResponse(
        incidents=incidents, page=Page(total=total, offset=offset, limit=limit)
    )


@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    request: Request,
    body: CreateIncidentRequest,
    idempotency_key: str | None = Header(default=None),
    principal: Principal = Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> IncidentResponse:
    ctx = _ctx(request)
    # A principal may only create incidents within a venue it can access.
    require_venue_access(principal, body.venue_id)
    # Idempotent replay: same key returns the stored response, no new incident.
    if idempotency_key:
        cached = ctx.idempotency.get("incident:create", idempotency_key)
        if cached is not None:
            return IncidentResponse(**cached["body"])
    problem = await ctx.client.get_problem(body.problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    incident = await ctx.incidents.create_from_problem(
        problem, venue_id=body.venue_id, match_id=body.match_id
    )
    response = IncidentResponse(incident=incident)
    if idempotency_key:
        ctx.idempotency.put(
            "incident:create", idempotency_key, 201,
            response.model_dump(mode="json"),
        )
    return response


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    request: Request, incident_id: str,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> IncidentResponse:
    incident = await _authorize_incident(request, incident_id, principal)
    return IncidentResponse(incident=incident)


@router.post("/{incident_id}/transition", response_model=IncidentResponse)
async def transition_incident(
    request: Request,
    incident_id: str,
    body: TransitionRequest,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> IncidentResponse:
    ctx = _ctx(request)
    await _authorize_incident(request, incident_id, principal)
    try:
        incident = await ctx.incidents.transition(
            incident_id, body.target, actor=body.actor, note=body.note,
            expected_version=body.expected_version,
        )
    except StaleVersionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IncidentError as exc:
        # 404 for missing, 409 for illegal transition.
        msg = str(exc)
        code = 404 if "not found" in msg else 409
        raise HTTPException(status_code=code, detail=msg) from exc
    return IncidentResponse(incident=incident)


@router.post("/{incident_id}/assign", response_model=IncidentResponse)
async def assign_incident(
    request: Request,
    incident_id: str,
    body: AssignRequest,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> IncidentResponse:
    ctx = _ctx(request)
    await _authorize_incident(request, incident_id, principal)
    try:
        incident = await ctx.incidents.assign(
            incident_id, body.assignee, actor=body.actor
        )
    except IncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return IncidentResponse(incident=incident)


@router.post("/{incident_id}/note", response_model=IncidentResponse)
async def add_note(
    request: Request,
    incident_id: str,
    body: NoteRequest,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> IncidentResponse:
    ctx = _ctx(request)
    await _authorize_incident(request, incident_id, principal)
    try:
        incident = await ctx.incidents.add_note(
            incident_id, body.note, actor=body.actor
        )
    except IncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return IncidentResponse(incident=incident)


@router.post("/{incident_id}/escalate", response_model=IncidentResponse)
async def escalate_incident(
    request: Request, incident_id: str,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> IncidentResponse:
    ctx = _ctx(request)
    await _authorize_incident(request, incident_id, principal)
    try:
        incident = await ctx.incidents.evaluate_escalation(incident_id)
    except IncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return IncidentResponse(incident=incident)
