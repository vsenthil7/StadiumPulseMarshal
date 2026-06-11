"""Incident lifecycle API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.auth import require_auth
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
from app.services.incident_service import IncidentError

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    request: Request,
    open_only: bool = False,
    venue_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _auth: dict = Depends(require_auth),
) -> IncidentListResponse:
    ctx = _ctx(request)
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
    _auth: dict = Depends(require_auth),
) -> IncidentResponse:
    ctx = _ctx(request)
    problem = await ctx.client.get_problem(body.problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    incident = await ctx.incidents.create_from_problem(
        problem, venue_id=body.venue_id, match_id=body.match_id
    )
    return IncidentResponse(incident=incident)


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    request: Request, incident_id: str, _auth: dict = Depends(require_auth)
) -> IncidentResponse:
    ctx = _ctx(request)
    incident = await ctx.incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentResponse(incident=incident)


@router.post("/{incident_id}/transition", response_model=IncidentResponse)
async def transition_incident(
    request: Request,
    incident_id: str,
    body: TransitionRequest,
    _auth: dict = Depends(require_auth),
) -> IncidentResponse:
    ctx = _ctx(request)
    try:
        incident = await ctx.incidents.transition(
            incident_id, body.target, actor=body.actor, note=body.note
        )
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
    _auth: dict = Depends(require_auth),
) -> IncidentResponse:
    ctx = _ctx(request)
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
    _auth: dict = Depends(require_auth),
) -> IncidentResponse:
    ctx = _ctx(request)
    try:
        incident = await ctx.incidents.add_note(
            incident_id, body.note, actor=body.actor
        )
    except IncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return IncidentResponse(incident=incident)


@router.post("/{incident_id}/escalate", response_model=IncidentResponse)
async def escalate_incident(
    request: Request, incident_id: str, _auth: dict = Depends(require_auth)
) -> IncidentResponse:
    ctx = _ctx(request)
    try:
        incident = await ctx.incidents.evaluate_escalation(incident_id)
    except IncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return IncidentResponse(incident=incident)
