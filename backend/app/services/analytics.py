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
