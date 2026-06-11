"""Runbook library API — CRUD + execute, RBAC-guarded."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import require_permission
from app.core.context import AppContext
from app.models.runbook import Runbook, RunbookCategory, RunbookStep
from app.rbac.policy import Permission, Principal

router = APIRouter(prefix="/api/v1", tags=["runbooks"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


class RunbookCreate(BaseModel):
    name: str
    category: RunbookCategory = RunbookCategory.INCIDENT
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    steps: list[RunbookStep] = Field(default_factory=list)
    owner: str = ""
    venue_ids: list[str] = Field(default_factory=list)


class RunbookExecuteBody(BaseModel):
    incident_id: str | None = None


@router.get("/runbooks", tags=["runbooks"])
async def list_runbooks(
    request: Request, category: RunbookCategory | None = None,
    tag: str | None = None, venue_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.RUNBOOK_READ)),
) -> dict:
    rbs = _ctx(request).runbooks.list_runbooks(category, tag, venue_id)
    return {"runbooks": [r.model_dump(mode="json") for r in rbs]}


@router.get("/runbooks/{runbook_id}", tags=["runbooks"])
async def get_runbook(
    runbook_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.RUNBOOK_READ)),
) -> dict:
    rb = _ctx(request).runbooks.get_runbook(runbook_id)
    if rb is None:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return rb.model_dump(mode="json")


@router.post("/runbooks", tags=["runbooks"])
async def create_runbook(
    body: RunbookCreate, request: Request,
    principal: Principal = Depends(require_permission(Permission.RUNBOOK_WRITE)),
) -> dict:
    rb = Runbook(**body.model_dump(), created_by=principal.subject)
    created = _ctx(request).runbooks.create_runbook(rb)
    return created.model_dump(mode="json")


@router.patch("/runbooks/{runbook_id}", tags=["runbooks"])
async def update_runbook(
    runbook_id: str, patch: dict, request: Request,
    _p: Principal = Depends(require_permission(Permission.RUNBOOK_WRITE)),
) -> dict:
    updated = _ctx(request).runbooks.update_runbook(runbook_id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return updated.model_dump(mode="json")


@router.delete("/runbooks/{runbook_id}", tags=["runbooks"])
async def delete_runbook(
    runbook_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.RUNBOOK_WRITE)),
) -> dict:
    ok = _ctx(request).runbooks.delete_runbook(runbook_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return {"deleted": True, "id": runbook_id}


@router.post("/runbooks/{runbook_id}/execute", tags=["runbooks"])
async def execute_runbook(
    runbook_id: str, body: RunbookExecuteBody, request: Request,
    principal: Principal = Depends(require_permission(Permission.RUNBOOK_WRITE)),
) -> dict:
    ex = await _ctx(request).runbooks.execute_runbook(
        runbook_id, actor=principal.subject, incident_id=body.incident_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return ex.model_dump(mode="json")


@router.get("/runbook-executions", tags=["runbooks"])
async def list_runbook_executions(
    request: Request, runbook_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.RUNBOOK_READ)),
) -> dict:
    exs = _ctx(request).runbooks.list_executions(runbook_id)
    return {"executions": [e.model_dump(mode="json") for e in exs]}
