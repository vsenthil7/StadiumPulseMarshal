"""Enterprise width endpoints: cost analytics, change events, fleet command."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import require_permission
from app.core.context import AppContext
from app.models.change_event import ChangeEvent, ChangeType
from app.rbac.policy import Permission, Principal

router = APIRouter(prefix="/api/v1", tags=["enterprise"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


# ── Cost / capacity analytics ───────────────────────────────────────────────
@router.get("/cost-analytics", tags=["enterprise"])
async def cost_analytics(
    request: Request, venue_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> dict:
    return _ctx(request).cost_analytics.summary(venue_id).model_dump(mode="json")


# ── Change events ───────────────────────────────────────────────────────────
class ChangeEventBody(BaseModel):
    title: str
    change_type: ChangeType = ChangeType.DEPLOYMENT
    service_id: str = ""
    venue_id: str | None = None
    metadata: dict = Field(default_factory=dict)


@router.get("/change-events", tags=["enterprise"])
async def list_change_events(
    request: Request, service_id: str | None = None,
    change_type: ChangeType | None = None,
    _p: Principal = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> dict:
    evs = _ctx(request).change_events.list(service_id, change_type)
    return {"events": [e.model_dump(mode="json") for e in evs]}


@router.post("/change-events", tags=["enterprise"])
async def record_change_event(
    body: ChangeEventBody, request: Request,
    principal: Principal = Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> dict:
    ev = ChangeEvent(**body.model_dump(), actor=principal.subject)
    return _ctx(request).change_events.record(ev).model_dump(mode="json")


@router.post("/change-events/{event_id}/link/{incident_id}", tags=["enterprise"])
async def link_change_event(
    event_id: str, incident_id: str, request: Request,
    _p: Principal = Depends(require_permission(Permission.INCIDENT_WRITE)),
) -> dict:
    ev = _ctx(request).change_events.link_incident(event_id, incident_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Change event not found")
    return ev.model_dump(mode="json")


@router.get("/change-events/correlate", tags=["enterprise"])
async def correlate_change_events(
    request: Request, incident_time: str, service_id: str | None = None,
    venue_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> dict:
    try:
        ts = datetime.fromisoformat(incident_time.replace(" ", "+"))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid incident_time (ISO 8601)")
    evs = _ctx(request).change_events.correlate(ts, service_id, venue_id)
    return {"events": [e.model_dump(mode="json") for e in evs]}


# ── Fleet command center ────────────────────────────────────────────────────
@router.get("/fleet", tags=["enterprise"])
async def fleet_summary(
    request: Request,
    principal: Principal = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> dict:
    """Per-venue operational rollup: incidents, SLO health, burn pressure."""
    ctx = _ctx(request)
    await ctx.ensure_entity_venue_map()
    venues = sorted(ctx.entity_venue.known_venues()) \
        if hasattr(ctx.entity_venue, "known_venues") else []
    if not venues:
        # Derive from analytics-by-venue when resolver doesn't expose a list.
        va = await ctx.analytics(
            principal_venues=None if principal.all_venues else principal.venues)
        return {"venues": [], "summary": {
            "total_incidents": va.total_incidents,
            "open_incidents": va.open_incidents,
            "slo_breaching": va.slo_breaching,
            "burn_active_silences": getattr(va, "burn_active_silences", 0)}}
    rows = []
    allowed = None if principal.all_venues else set(principal.venues)
    for vid in venues:
        if allowed is not None and vid not in allowed:
            continue
        v = await ctx.analytics(principal_venues=None, venue_filter=vid)
        rows.append({
            "venue_id": vid,
            "open_incidents": v.open_incidents,
            "total_incidents": v.total_incidents,
            "slo_breaching": v.slo_breaching,
            "slo_total": v.slo_total,
            "burn_page_alerts": getattr(v, "burn_page_alerts", 0),
            "burn_active_silences": getattr(v, "burn_active_silences", 0),
        })
    return {"venues": rows, "venue_count": len(rows)}
