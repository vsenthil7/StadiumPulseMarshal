"""Postmortem workflow API — RBAC-guarded."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.auth import require_permission
from app.core.context import AppContext
from app.models.postmortem import Postmortem, PostmortemStatus
from app.rbac.policy import Permission, Principal

router = APIRouter(prefix="/api/v1", tags=["postmortems"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


class PostmortemCreate(BaseModel):
    title: str
    incident_id: str | None = None
    severity: str = ""
    summary: str = ""
    venue_id: str | None = None


class TimelineBody(BaseModel):
    text: str


class ActionBody(BaseModel):
    description: str
    owner: str = ""
    due: str | None = None


@router.get("/postmortems", tags=["postmortems"])
async def list_postmortems(
    request: Request, status: PostmortemStatus | None = None,
    incident_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.POSTMORTEM_READ)),
) -> dict:
    pms = _ctx(request).postmortems.list(status, incident_id)
    return {"postmortems": [p.model_dump(mode="json") for p in pms]}


@router.get("/postmortems/{pm_id}", tags=["postmortems"])
async def get_postmortem(
    pm_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.POSTMORTEM_READ)),
) -> dict:
    pm = _ctx(request).postmortems.get(pm_id)
    if pm is None:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return pm.model_dump(mode="json")


@router.post("/postmortems", tags=["postmortems"])
async def create_postmortem(
    body: PostmortemCreate, request: Request,
    principal: Principal = Depends(require_permission(Permission.POSTMORTEM_WRITE)),
) -> dict:
    pm = Postmortem(**body.model_dump(), created_by=principal.subject)
    pm = await _ctx(request).postmortems.create(pm)
    return pm.model_dump(mode="json")


@router.patch("/postmortems/{pm_id}", tags=["postmortems"])
async def update_postmortem(
    pm_id: str, patch: dict, request: Request,
    _p: Principal = Depends(require_permission(Permission.POSTMORTEM_WRITE)),
) -> dict:
    pm = await _ctx(request).postmortems.update(pm_id, patch)
    if pm is None:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return pm.model_dump(mode="json")


@router.post("/postmortems/{pm_id}/timeline", tags=["postmortems"])
async def add_timeline(
    pm_id: str, body: TimelineBody, request: Request,
    principal: Principal = Depends(require_permission(Permission.POSTMORTEM_WRITE)),
) -> dict:
    pm = await _ctx(request).postmortems.add_timeline(pm_id, body.text, principal.subject)
    if pm is None:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return pm.model_dump(mode="json")


@router.post("/postmortems/{pm_id}/actions", tags=["postmortems"])
async def add_action(
    pm_id: str, body: ActionBody, request: Request,
    _p: Principal = Depends(require_permission(Permission.POSTMORTEM_WRITE)),
) -> dict:
    pm = await _ctx(request).postmortems.add_action(pm_id, body.description, body.owner, body.due)
    if pm is None:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return pm.model_dump(mode="json")


@router.post("/postmortems/{pm_id}/actions/{action_id}/complete", tags=["postmortems"])
async def complete_action(
    pm_id: str, action_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.POSTMORTEM_WRITE)),
) -> dict:
    pm = await _ctx(request).postmortems.complete_action(pm_id, action_id)
    if pm is None:
        raise HTTPException(status_code=404, detail="Postmortem or action not found")
    return pm.model_dump(mode="json")


@router.post("/postmortems/{pm_id}/publish", tags=["postmortems"])
async def publish_postmortem(
    pm_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.POSTMORTEM_WRITE)),
) -> dict:
    pm = await _ctx(request).postmortems.publish(pm_id)
    if pm is None:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return pm.model_dump(mode="json")


@router.get("/postmortems/{pm_id}/export", tags=["postmortems"],
            response_class=PlainTextResponse)
async def export_postmortem(
    pm_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.POSTMORTEM_READ)),
) -> str:
    md = _ctx(request).postmortems.export_markdown(pm_id)
    if md is None:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return md
