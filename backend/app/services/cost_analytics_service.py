"""Cost / capacity analytics service (synthetic, deterministic seed)."""
from __future__ import annotations

from app.models.cost_analytics import CostSummary, ServiceCost

# Deterministic seed so the demo is stable; in live mode this would pull from
# Cloud Billing + Dynatrace utilisation metrics.
_SEED: list[dict] = [
    {"service_id": "SVC-PAYMENTS", "service_name": "Payments",
     "monthly_cost_usd": 4200.0, "cpu_utilisation": 0.72,
     "memory_utilisation": 0.65, "instance_count": 6, "venue_id": None},
    {"service_id": "SVC-TICKETING", "service_name": "Ticketing",
     "monthly_cost_usd": 3100.0, "cpu_utilisation": 0.18,
     "memory_utilisation": 0.22, "instance_count": 8, "venue_id": None},
    {"service_id": "SVC-STREAMING", "service_name": "Streaming",
     "monthly_cost_usd": 9800.0, "cpu_utilisation": 0.91,
     "memory_utilisation": 0.88, "instance_count": 12, "venue_id": None},
    {"service_id": "SVC-CONCESSIONS", "service_name": "Concessions",
     "monthly_cost_usd": 1400.0, "cpu_utilisation": 0.12,
     "memory_utilisation": 0.15, "instance_count": 4, "venue_id": None},
]


def _rightsize(cpu: float, mem: float) -> str:
    util = max(cpu, mem)
    if util < 0.25:
        return "downsize"
    if util > 0.85:
        return "upsize"
    return "ok"


class CostAnalyticsService:
    def __init__(self) -> None:
        self._services = [ServiceCost(**s, rightsizing=_rightsize(
            s["cpu_utilisation"], s["memory_utilisation"])) for s in _SEED]

    def summary(self, venue_id: str | None = None) -> CostSummary:
        svcs = self._services
        if venue_id:
            svcs = [s for s in svcs if s.venue_id in (None, venue_id)]
        total = round(sum(s.monthly_cost_usd for s in svcs), 2)
        down = sum(1 for s in svcs if s.rightsizing == "downsize")
        up = sum(1 for s in svcs if s.rightsizing == "upsize")
        return CostSummary(total_monthly_cost_usd=total, services=svcs,
                           downsize_candidates=down, upsize_candidates=up)
