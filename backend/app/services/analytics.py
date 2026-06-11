"""Analytics service: operational metrics over incidents.

Computes MTTR/MTTA, counts by severity/state/phase, and SLO breach summaries for
the analytics dashboard. Pure aggregation over repository data.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.incident import Incident
from app.models.slo import ErrorBudget


class AnalyticsSummary(BaseModel):
    total_incidents: int = 0
    open_incidents: int = 0
    resolved_incidents: int = 0
    mttr_minutes: float | None = None
    mtta_minutes: float | None = None
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_state: dict[str, int] = Field(default_factory=dict)
    by_venue: dict[str, int] = Field(default_factory=dict)
    slo_breaching: int = 0
    slo_total: int = 0
    burn_page_alerts: int = 0
    burn_ticket_alerts: int = 0


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def compute_summary(
    incidents: list[Incident], budgets: list[ErrorBudget]
) -> AnalyticsSummary:
    summary = AnalyticsSummary(total_incidents=len(incidents))

    ttrs: list[float] = []
    ttas: list[float] = []
    for inc in incidents:
        if inc.is_open:
            summary.open_incidents += 1
        else:
            summary.resolved_incidents += 1
        if inc.ttr_minutes is not None:
            ttrs.append(inc.ttr_minutes)
        if inc.tta_minutes is not None:
            ttas.append(inc.tta_minutes)

        sev = inc.severity.value
        summary.by_severity[sev] = summary.by_severity.get(sev, 0) + 1
        st = inc.state.value
        summary.by_state[st] = summary.by_state.get(st, 0) + 1
        if inc.venue_id:
            summary.by_venue[inc.venue_id] = (
                summary.by_venue.get(inc.venue_id, 0) + 1
            )

    summary.mttr_minutes = _mean(ttrs)
    summary.mtta_minutes = _mean(ttas)
    summary.slo_total = len(budgets)
    summary.slo_breaching = sum(1 for b in budgets if b.is_breaching)
    return summary


class VenueAnalytics(BaseModel):
    """Per-venue operational rollup for the venue dashboard."""

    venue_id: str
    total_incidents: int = 0
    open_incidents: int = 0
    resolved_incidents: int = 0
    mttr_minutes: float | None = None
    mtta_minutes: float | None = None
    by_severity: dict[str, int] = Field(default_factory=dict)
    slo_total: int = 0
    slo_breaching: int = 0
    slo_health: float = 100.0  # % of SLOs not breaching


class VenueAnalyticsResponse(BaseModel):
    venues: list[VenueAnalytics] = Field(default_factory=list)


def compute_by_venue(
    incidents: list[Incident],
    budgets_by_venue: dict[str, list[ErrorBudget]],
    venues: list[str],
) -> list[VenueAnalytics]:
    """Build per-venue rollups for the supplied venue ids.

    ``budgets_by_venue`` maps a venue id to the SLO budgets owned by that venue
    (resolved by the caller via the entity→venue resolver). ``venues`` is the
    set the principal may see, so the result is already scoped.
    """
    out: list[VenueAnalytics] = []
    for vid in venues:
        v_inc = [i for i in incidents if i.venue_id == vid]
        va = VenueAnalytics(venue_id=vid, total_incidents=len(v_inc))
        ttrs: list[float] = []
        ttas: list[float] = []
        for inc in v_inc:
            if inc.is_open:
                va.open_incidents += 1
            else:
                va.resolved_incidents += 1
            if inc.ttr_minutes is not None:
                ttrs.append(inc.ttr_minutes)
            if inc.tta_minutes is not None:
                ttas.append(inc.tta_minutes)
            sev = inc.severity.value
            va.by_severity[sev] = va.by_severity.get(sev, 0) + 1
        va.mttr_minutes = _mean(ttrs)
        va.mtta_minutes = _mean(ttas)
        budgets = budgets_by_venue.get(vid, [])
        va.slo_total = len(budgets)
        va.slo_breaching = sum(1 for b in budgets if b.is_breaching)
        if va.slo_total:
            va.slo_health = round(
                100.0 * (va.slo_total - va.slo_breaching) / va.slo_total, 1
            )
        out.append(va)
    return out
