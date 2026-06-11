"""Audit log query endpoint (cursor-paginated)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.auth import require_permission
from app.core.context import AppContext
from app.models.audit import AuditEntry
from app.rbac.policy import Permission

router = APIRouter(prefix="/api/v1/audit-log", tags=["audit"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


class AuditCursorPage(BaseModel):
    limit: int
    next_cursor: str | None = None
    has_more: bool = False


class AuditQueryResponse(BaseModel):
    entries: list[AuditEntry] = Field(default_factory=list)
    page: AuditCursorPage


@router.get("", response_model=AuditQueryResponse)
async def query_audit(
    request: Request,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _p=Depends(require_permission(Permission.ANALYTICS_READ)),
) -> AuditQueryResponse:
    ctx = _ctx(request)
    # Fetch one extra to determine has_more without a second query.
    entries = await ctx.audit.query(
        resource_type=resource_type, resource_id=resource_id, actor=actor,
        action=action, after_cursor=cursor, limit=limit + 1,
    )
    has_more = len(entries) > limit
    page_entries = entries[:limit]
    next_cursor = page_entries[-1].id if page_entries and has_more else None
    return AuditQueryResponse(
        entries=page_entries,
        page=AuditCursorPage(
            limit=limit, next_cursor=next_cursor, has_more=has_more
        ),
    )
