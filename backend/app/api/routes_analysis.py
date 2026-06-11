"""Routes for SLO trends, postmortems, incident search and bulk operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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


@router.get("/slo/burn-digest", tags=["slo"])
async def slo_burn_digest(
    request: Request, hours: float = 24.0, min_severity: str = "ticket",
    dispatch: bool = False,
    principal: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> dict:
    """Preview (or dispatch) the burn/suppression digest.

    ``dispatch=true`` sends it on the configured channel (responder+ required).
    """
    from app.services.digest_service import compose_digest

    ctx = _ctx(request)
    msg = await compose_digest(ctx, hours, min_severity)
    sent = False
    if dispatch:
        if not principal.has(Permission.REMEDIATION_APPROVE):
            raise HTTPException(status_code=403, detail="dispatch requires responder")
        from app.models.notification import NotificationChannel

        ch_name = ctx.settings.burn_digest_channel
        ch = NotificationChannel(ch_name) \
            if ch_name in {c.value for c in NotificationChannel} \
            else NotificationChannel.SLACK
        await ctx.notifications.notify_digest(
            msg, channel=ch, recipient=ctx.settings.burn_digest_recipient)
        sent = True
    return {"digest": msg, "dispatched": sent}


@router.get("/slo/burn-by-venue", tags=["slo"])
async def slo_burn_by_venue(
    request: Request,
    principal: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> dict:
    """Per-venue burn breakdown: page/ticket alert counts + active acks/silences.

    Scoped to the principal's venues. Lets the console compare burn pressure and
    suppression across venues at a glance.
    """
    ctx = _ctx(request)
    alerts = await ctx.burn_alerts(
        principal_venues=None if principal.all_venues else principal.venues,
    )
    active = await ctx.burn_acks.active_summary()
    venues: dict[str, dict] = {}

    def _row(vid: str) -> dict:
        return venues.setdefault(vid, {
            "venue_id": vid, "page": 0, "ticket": 0,
            "active_acks": 0, "active_silences": 0,
        })

    for a in alerts:
        vid = a.venue_id or "unassigned"
        row = _row(vid)
        sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
        if sev in ("page", "ticket"):
            row[sev] += 1
    for a in active["acks"]:
        vid = _scope_venue(ctx, a.get("slo_id", "")) or "unassigned"
        _row(vid)["active_acks"] += 1
    for s in active["silences"]:
        vid = _scope_venue(ctx, s.get("slo_id", "")) or "unassigned"
        _row(vid)["active_silences"] += 1

    if not principal.all_venues:
        allowed = set(principal.venues)
        venues = {k: v for k, v in venues.items()
                  if k in allowed or k == "unassigned"}
    return {"venues": sorted(venues.values(), key=lambda r: r["venue_id"])}


def _scope_venue(ctx, slo_id: str) -> str | None:
    slo = next((x for x in ctx.slo_engine.slos if x.id == slo_id), None)
    if slo is None:
        return None
    return ctx.entity_venue.venue_for(slo.service_id)


@router.get("/slo/burn-trend", tags=["slo"])
async def slo_burn_trend(
    request: Request, hours: float = 24.0, buckets: int = 12,
    venue_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> dict:
    """Bucketed ack/silence counts over a trailing window (for a trend chart).

    Prefers pre-aggregated counter buckets; falls back to the audit trail when
    counters are empty. Optional ``venue_id`` filter.
    """
    from datetime import datetime, timezone

    ctx = _ctx(request)
    now = datetime.now(timezone.utc).timestamp()
    span = hours * 3600
    start = now - span
    buckets = max(1, min(buckets, 60))
    width = span / buckets
    series = [
        {"index": i, "ack": 0, "silence": 0, "unack": 0, "unsilence": 0,
         "start_epoch": round(start + i * width, 1)}
        for i in range(buckets)
    ]

    def _bucket_index(ts: float) -> int:
        return min(buckets - 1, max(0, int((ts - start) / width)))

    if await ctx.burn_counters.any_recorded():
        from app.services.burn_counters import BUCKET_SECONDS

        ctr = await ctx.burn_counters.buckets(
            int(start // BUCKET_SECONDS) * BUCKET_SECONDS, venue_id)
        for bucket_epoch, actions in ctr.items():
            if bucket_epoch < start or bucket_epoch > now:
                continue
            idx = _bucket_index(bucket_epoch)
            for verb, n in actions.items():
                if verb in series[idx]:
                    series[idx][verb] += n
    else:
        entries = await ctx.audit.query(resource_type="burn_alert", limit=10_000)
        for e in entries:
            ts = e.at.timestamp()
            if ts < start or ts > now:
                continue
            verb = e.action.replace("burn.", "")
            if verb in ("ack", "silence", "unack", "unsilence"):
                series[_bucket_index(ts)][verb] += 1

    return {"window_hours": hours, "bucket_width_seconds": round(width, 1),
            "venue_id": venue_id, "buckets": _with_net_active(series)}


def _with_net_active(series: list[dict]) -> list[dict]:
    """Annotate each bucket with a running net-active silence count
    (cumulative silence − unsilence up to and including that bucket)."""
    running = 0
    for b in series:
        running += b.get("silence", 0) - b.get("unsilence", 0)
        b["net_active"] = max(0, running)
    return series


@router.get("/slo/burn-stats", tags=["slo"])
async def slo_burn_stats(
    request: Request, hours: float = 24.0, venue_id: str | None = None,
    _p: Principal = Depends(require_permission(Permission.SLO_READ)),
) -> dict:
    """Burn-alert response analytics: counts, suppression ratio, active state.

    Reads pre-aggregated counters first (no audit scan); falls back to the audit
    trail when counters are empty (e.g. fresh KV after restart). Optional
    ``venue_id`` filter.
    """
    ctx = _ctx(request)
    counts: dict[str, int]
    per_target: dict[str, dict[str, int]] = {}
    most_silenced: list[dict] = []

    if await ctx.burn_counters.any_recorded():
        counts = await ctx.burn_counters.totals(venue_id)
    else:
        from datetime import datetime, timezone

        entries = await ctx.audit.query(resource_type="burn_alert", limit=10_000)
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        counts = {"ack": 0, "silence": 0, "unack": 0, "unsilence": 0}
        for e in entries:
            if e.at.timestamp() < cutoff:
                continue
            verb = e.action.replace("burn.", "")
            if verb in counts:
                counts[verb] += 1
                t = per_target.setdefault(e.resource_id, {"ack": 0, "silence": 0})
                if verb in t:
                    t[verb] += 1
        most_silenced = sorted(
            ({"target": k, **v} for k, v in per_target.items()),
            key=lambda r: r["silence"], reverse=True,
        )[:5]

    acks = counts.get("ack", 0)
    silences = counts.get("silence", 0)
    denom = acks + silences
    suppression_ratio = round(silences / denom, 3) if denom else 0.0
    active = await ctx.burn_acks.active_summary()
    if venue_id is not None:
        active_acks = sum(1 for a in active["acks"] if _scope_match(ctx, a, venue_id))
        active_silences = sum(1 for s in active["silences"] if _scope_match(ctx, s, venue_id))
    else:
        active_acks = len(active["acks"])
        active_silences = len(active["silences"])
    return {
        "window_hours": hours, "venue_id": venue_id, "counts": counts,
        "suppression_ratio": suppression_ratio,
        "active_acks": active_acks, "active_silences": active_silences,
        "most_silenced": most_silenced,
    }


def _scope_match(ctx, entry: dict, venue_id: str) -> bool:
    slo_id = entry.get("slo_id", "")
    slo = next((x for x in ctx.slo_engine.slos if x.id == slo_id), None)
    if slo is None:
        return False
    return ctx.entity_venue.venue_for(slo.service_id) == venue_id


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


async def _burn_venue_for(ctx, slo_id: str):
    """Resolve the owning venue for an SLO id (for venue-keyed counters)."""
    try:
        await ctx.ensure_entity_venue_map()
        slo = next((x for x in ctx.slo_engine.slos if x.id == slo_id), None)
        if slo is not None:
            return ctx.entity_venue.venue_for(slo.service_id)
    except Exception:  # noqa: BLE001
        pass
    return None


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
    await ctx.burn_counters.record("ack", await _burn_venue_for(ctx, slo_id))
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
    await ctx.burn_counters.record("silence", await _burn_venue_for(ctx, slo_id))
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
