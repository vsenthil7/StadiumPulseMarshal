"""SLO, analytics, notifications and scenario API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth import require_permission, require_venue_access
from app.rbac.policy import Permission, Principal
from app.api.schemas_ext import (
    AnalyticsResponse,
    NotificationListResponse,
    ScenarioInfo,
    ScenarioListResponse,
    SelectScenarioRequest,
    SLOListResponse,
)
from app.core.context import AppContext
from app.services.analytics import VenueAnalyticsResponse
from app.fixtures.scenarios.registry import all_scenarios

router = APIRouter(prefix="/api/v1", tags=["ops"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


@router.get("/slo", response_model=SLOListResponse, tags=["slo"])
async def list_slo_budgets(
    request: Request, venue_id: str | None = None,
    principal: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> SLOListResponse:
    ctx = _ctx(request)
    await ctx.ensure_entity_venue_map()
    budgets = await ctx.evaluate_slos()
    if venue_id is not None:
        require_venue_access(principal, venue_id)
    # Map slo_id → owning entity → venue, then keep budgets the caller may see.
    slo_entity = {s.id: s.service_id for s in ctx.slo_engine.slos}
    def _venue_of(budget) -> str | None:
        return ctx.entity_venue.venue_for(slo_entity.get(budget.slo_id))
    if venue_id is not None:
        budgets = [b for b in budgets if _venue_of(b) in (None, venue_id)]
    elif not principal.all_venues:
        allowed = set(principal.venues)
        budgets = [b for b in budgets
                   if (_venue_of(b) is None) or (_venue_of(b) in allowed)]
    return SLOListResponse(budgets=budgets)


@router.get(
    "/analytics/by-venue",
    response_model=VenueAnalyticsResponse,
    tags=["analytics"],
)
async def get_analytics_by_venue(
    request: Request,
    principal: Principal = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> VenueAnalyticsResponse:
    ctx = _ctx(request)
    venues = await ctx.analytics_by_venue(
        principal_venues=None if principal.all_venues else principal.venues,
    )
    return VenueAnalyticsResponse(venues=venues)


@router.get("/analytics", response_model=AnalyticsResponse, tags=["analytics"])
async def get_analytics(
    request: Request, venue_id: str | None = None,
    principal: Principal = Depends(require_permission(Permission.ANALYTICS_READ)),
) -> AnalyticsResponse:
    ctx = _ctx(request)
    if venue_id is not None:
        require_venue_access(principal, venue_id)
    return AnalyticsResponse(summary=await ctx.analytics(
        principal_venues=None if principal.all_venues else principal.venues,
        venue_filter=venue_id,
    ))


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    tags=["notifications"],
)
async def list_notifications(
    request: Request,
    incident_id: str | None = None,
    source: str | None = None,
    severity: str | None = None,
    _p=Depends(require_permission(Permission.INCIDENT_READ)),
) -> NotificationListResponse:
    ctx = _ctx(request)
    notifications = await ctx.notifications.list_all() if incident_id is None \
        else await ctx.notifications.list_for_incident(incident_id)
    if source is not None:
        notifications = [
            n for n in notifications
            if getattr(n.source, "value", n.source) == source
        ]
    if severity is not None:
        notifications = [n for n in notifications if n.severity == severity]
    return NotificationListResponse(notifications=notifications)


@router.get("/slo/{slo_id}/metric-preview", tags=["slo"])
async def slo_metric_preview(
    slo_id: str, request: Request, lookback_hours: float = 6.0,
    principal: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> dict:
    """Preview the metric selector + sample error series for an SLO.

    Lets an operator confirm a (live or synthetic) metric selector resolves and
    see the per-window error rates that burn evaluation would use, before relying
    on it. Venue-scoped via the SLO's owning entity.
    """
    ctx = _ctx(request)
    slo = next((s for s in ctx.slo_engine.slos if s.id == slo_id), None)
    if slo is None:
        raise HTTPException(status_code=404, detail="SLO not found")
    await ctx.ensure_entity_venue_map()
    venue = ctx.entity_venue.venue_for(slo.service_id)
    require_venue_access(principal, venue)

    from app.services.metrics_source import _metric_selector_for

    selector = _metric_selector_for(slo, ctx.settings)
    try:
        samples = await ctx.metrics_source.error_series(slo, lookback_hours)
    except Exception:  # noqa: BLE001
        samples = []
    # Per-window rates the burn engine would compute.
    import time as _t

    hist_preview = {}
    from app.services.metrics_history import MetricsHistory

    mh = MetricsHistory()
    for s in samples:
        mh.record(slo.id, s.error_rate, weight=s.weight, at=s.at)
    for label, hours in (("5m", 5 / 60), ("1h", 1.0), ("6h", 6.0)):
        rate = mh.error_rate_over(slo.id, hours)
        hist_preview[label] = round(rate, 5) if rate is not None else None
    return {
        "slo_id": slo.id, "slo_name": slo.name, "sli_kind": slo.sli.kind.value,
        "service_id": slo.service_id, "venue_id": venue,
        "metric_selector": selector,
        "sample_count": len(samples),
        "window_error_rates": hist_preview,
        "points": [
            {"at": round(s.at, 1), "error_rate": round(s.error_rate, 5)}
            for s in samples[-20:]
        ],
    }


@router.get("/oncall", tags=["oncall"])
async def get_oncall(
    request: Request,
    _p=Depends(require_permission(Permission.INCIDENT_READ)),
) -> dict:
    """On-call roster, escalation policies, and current burn-alert targets.

    Read-only operational reference for the On-call console: who is on each tier,
    the escalation ladders, and which on-call targets a page/ticket burn alert
    would notify (so SREs can see routing before an alert fires).
    """
    ctx = _ctx(request)
    await ctx.refresh_oncall()
    esc = ctx.escalation
    roster = [
        {
            "id": e.id, "name": e.name, "tier": e.tier.value,
            "handle": e.handle, "channels": e.channels,
        }
        for e in ctx.oncall_directory.roster
    ]
    policies = [
        {
            "id": p.id, "name": p.name, "min_severity": p.min_severity.value,
            "steps": [
                {"tier": s.tier.value, "after_minutes": s.after_minutes,
                 "notify_channels": s.notify_channels}
                for s in p.steps
            ],
        }
        for p in esc._policies
    ]
    burn_targets = {
        sev: [
            {"name": t.name, "tier": t.tier.value, "recipient": t.recipient,
             "channels": [c.value for c in t.channels]}
            for t in ctx.oncall_directory.targets_for_severity(sev)
        ]
        for sev in ("page", "ticket")
    }
    # Surface schedule provenance + next handoff when a rotating schedule is used.
    import time as _time

    src = ctx.schedule_source
    schedule = {"type": type(src).__name__}
    if hasattr(src, "next_handoff"):
        schedule["next_handoff_epoch"] = src.next_handoff()
        schedule["now_epoch"] = _time.time()
    if hasattr(src, "pool_view"):
        schedule["rotation"] = src.pool_view()
    ack_state = await ctx.burn_acks.active_summary()
    return {
        "roster": roster, "policies": policies, "burn_targets": burn_targets,
        "schedule": schedule, "ack_state": ack_state,
    }


@router.get("/scenarios", response_model=ScenarioListResponse, tags=["scenarios"])
async def list_scenarios(
    request: Request, _p=Depends(require_permission(Permission.INCIDENT_READ))
) -> ScenarioListResponse:
    ctx = _ctx(request)
    infos = [
        ScenarioInfo(
            key=s.key,
            name=s.name,
            description=s.description,
            venue=s.venue.name,
            match=s.match.label,
            severity=(s.problems[0].severity.value if s.problems else "INFO"),
        )
        for s in all_scenarios()
    ]
    return ScenarioListResponse(scenarios=infos, active=ctx.current_scenario)


@router.post("/scenarios/select", response_model=ScenarioListResponse,
             tags=["scenarios"])
async def select_scenario(
    request: Request,
    body: SelectScenarioRequest,
    _p=Depends(require_permission(Permission.SCENARIO_WRITE)),
) -> ScenarioListResponse:
    ctx = _ctx(request)
    ctx.set_scenario(body.key)
    return await list_scenarios(request)  # type: ignore[return-value]
