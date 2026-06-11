"""Routes for SLO trends, postmortems, incident search and bulk operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.auth import require_permission, require_venue_access, scope_collection
from app.api.schemas_ext import IncidentListResponse, Page
from app.core.context import AppContext
from app.core.errors import NotFoundError
from app.models.enums import Severity
from app.models.incident import IncidentState
from app.models.slo import BurnAlertList
from app.rbac.policy import Permission, Principal
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


@router.get("/slo/burn-events", tags=["slo"])
async def slo_burn_events(
    request: Request, limit: int = 50, offset: int = 0,
    action: str | None = None, fmt: str | None = None,
    _p: Principal = Depends(require_permission(Permission.REMEDIATION_APPROVE)),
):
    """Burn-alert ack/silence audit history (responder+).

    burn.ack / burn.silence / burn.unack / burn.unsilence entries, newest first.
    Supports ``action`` filter, ``offset``/``limit`` pagination, and ``fmt=csv``.
    """
    ctx = _ctx(request)
    entries = await ctx.audit.query(resource_type="burn_alert", limit=10_000)
    rows = [
        {
            "id": e.id, "at": e.at.isoformat(), "actor": e.actor,
            "action": e.action, "target": e.resource_id, "detail": e.metadata,
        }
        for e in entries
        if action is None or e.action == action
    ]
    rows.sort(key=lambda r: r["at"], reverse=True)
    total = len(rows)
    page = rows[offset:offset + limit]

    if fmt == "csv":
        import csv
        import io

        from fastapi.responses import StreamingResponse

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["timestamp", "actor", "action", "target"])
        for r in page:
            w.writerow([r["at"], r["actor"], r["action"], r["target"]])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=burn-events.csv"},
        )

    return {"events": page, "total": total, "offset": offset, "limit": limit}


@router.get("/slo/burn-stats", tags=["slo"])
async def slo_burn_stats(
    request: Request, hours: float = 24.0,
    _p: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> dict:
    """Burn-alert response analytics over a trailing window.

    Aggregates the ack/silence audit trail into counts and a suppression ratio
    (silences vs acknowledgements), plus the count of currently-active
    acks/silences. Helps spot alerts that are habitually silenced rather than
    acted on.
    """
    import time as _t
    from datetime import datetime, timezone

    ctx = _ctx(request)
    entries = await ctx.audit.query(resource_type="burn_alert", limit=10_000)
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    counts = {"ack": 0, "silence": 0, "unack": 0, "unsilence": 0}
    per_target: dict[str, dict[str, int]] = {}
    for e in entries:
        if e.at.timestamp() < cutoff:
            continue
        verb = e.action.replace("burn.", "")
        if verb in counts:
            counts[verb] += 1
            t = per_target.setdefault(e.resource_id, {"ack": 0, "silence": 0})
            if verb in t:
                t[verb] += 1
    acks = counts["ack"]
    silences = counts["silence"]
    denom = acks + silences
    suppression_ratio = round(silences / denom, 3) if denom else 0.0
    # Targets most often silenced (candidate noisy alerts).
    noisy = sorted(
        ({"target": k, **v} for k, v in per_target.items()),
        key=lambda r: r["silence"], reverse=True,
    )[:5]
    active = await ctx.burn_acks.active_summary()
    return {
        "window_hours": hours,
        "counts": counts,
        "suppression_ratio": suppression_ratio,
        "active_acks": len(active["acks"]),
        "active_silences": len(active["silences"]),
        "most_silenced": noisy,
    }


@router.get("/slo/burn-alerts", response_model=BurnAlertList, tags=["slo"])
async def slo_burn_alerts(
    request: Request,
    principal: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> BurnAlertList:
    """Multi-window burn-rate alerts, scoped to the principal's venues."""
    ctx = _ctx(request)
    alerts = await ctx.burn_alerts(
        principal_venues=None if principal.all_venues else principal.venues,
        notify=True,
    )
    return BurnAlertList(
        alerts=alerts,
        page_count=sum(1 for a in alerts if a.severity.value == "page"),
        ticket_count=sum(1 for a in alerts if a.severity.value == "ticket"),
        acked_count=sum(1 for a in alerts if a.acknowledged),
        silenced_count=sum(1 for a in alerts if a.silenced),
    )


class _AckBody(BaseModel):
    severity: str
    note: str = ""


class _SilenceBody(BaseModel):
    severity: str
    minutes: float = 60.0


@router.post("/slo/burn-alerts/{slo_id}/ack", tags=["slo"])
async def ack_burn_alert(
    slo_id: str, body: _AckBody, request: Request,
    principal: Principal = Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> dict:
    """Acknowledge a burn alert (responder+). Recorded with who/when + audited."""
    ctx = _ctx(request)
    rec = await ctx.burn_acks.acknowledge(slo_id, body.severity, principal.subject, body.note)
    try:
        await ctx.audit.record(
            actor=principal.subject, action="burn.ack",
            resource_type="burn_alert", resource_id=f"{slo_id}:{body.severity}",
            metadata={"note": body.note},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"acknowledged": True, "by": rec.acked_by, "at": rec.acked_at}


@router.post("/slo/burn-alerts/{slo_id}/silence", tags=["slo"])
async def silence_burn_alert(
    slo_id: str, body: _SilenceBody, request: Request,
    principal: Principal = Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> dict:
    """Silence a burn alert for N minutes (responder+); suppresses dispatch."""
    ctx = _ctx(request)
    rec = await ctx.burn_acks.silence(slo_id, body.severity, body.minutes, principal.subject)
    try:
        await ctx.audit.record(
            actor=principal.subject, action="burn.silence",
            resource_type="burn_alert", resource_id=f"{slo_id}:{body.severity}",
            metadata={"minutes": body.minutes},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"silenced": True, "until": rec.until, "by": rec.by}


@router.delete("/slo/burn-alerts/{slo_id}/ack", tags=["slo"])
async def unack_burn_alert(
    slo_id: str, severity: str, request: Request,
    principal: Principal = Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> dict:
    """Clear an acknowledgement (responder+); audited."""
    ctx = _ctx(request)
    cleared = await ctx.burn_acks.clear_ack(slo_id, severity)
    try:
        await ctx.audit.record(
            actor=principal.subject, action="burn.unack",
            resource_type="burn_alert", resource_id=f"{slo_id}:{severity}",
            metadata={},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"cleared": cleared}


@router.delete("/slo/burn-alerts/{slo_id}/silence", tags=["slo"])
async def unsilence_burn_alert(
    slo_id: str, severity: str, request: Request,
    principal: Principal = Depends(require_permission(Permission.REMEDIATION_APPROVE)),
) -> dict:
    """Lift a silence early (responder+); audited."""
    ctx = _ctx(request)
    cleared = await ctx.burn_acks.clear_silence(slo_id, severity)
    try:
        await ctx.audit.record(
            actor=principal.subject, action="burn.unsilence",
            resource_type="burn_alert", resource_id=f"{slo_id}:{severity}",
            metadata={},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"cleared": cleared}


@router.get("/slo/trends", response_model=SLOTrendResponse, tags=["slo"])
async def slo_trends(
    request: Request,
    venue_id: str | None = None,
    principal: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> SLOTrendResponse:
    ctx = _ctx(request)
    await ctx.ensure_entity_venue_map()
    # Ensure at least one sample exists.
    await ctx.evaluate_slos()
    trends = ctx.slo_history.all_trends()
    slo_entity = {s.id: s.service_id for s in ctx.slo_engine.slos}
    def _venue_of(t):
        return ctx.entity_venue.venue_for(slo_entity.get(t.slo_id))
    if venue_id is not None:
        require_venue_access(principal, venue_id)
        trends = [t for t in trends if _venue_of(t) in (None, venue_id)]
    elif not principal.all_venues:
        allowed = set(principal.venues)
        trends = [t for t in trends if _venue_of(t) is None or _venue_of(t) in allowed]
    return SLOTrendResponse(trends=trends)


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
    principal: Principal = Depends(require_permission(Permission.INCIDENT_READ)),
) -> IncidentListResponse:
    ctx = _ctx(request)
    results, total = await ctx.incidents.search(
        state=state, severity=severity, text=text, venue_id=venue_id,
        offset=offset, limit=limit,
    )
    scoped = scope_collection(principal, results, venue_id)
    return IncidentListResponse(
        incidents=scoped,
        page=Page(total=total if principal.all_venues else len(scoped),
                  offset=offset, limit=limit),
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
