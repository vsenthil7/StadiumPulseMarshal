"""SLO snapshot history and trend computation.

Each evaluation can be snapshotted; trends summarise the recent series per SLO
(latest state, min/max/avg burn rate, direction). In-memory ring buffer per SLO;
swappable for a time-series store behind the same interface.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.slo import ErrorBudget


class SLOSnapshot(BaseModel):
    slo_id: str
    slo_name: str
    state: str
    burn_rate: float
    consumed_fraction: float
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SLOTrend(BaseModel):
    slo_id: str
    slo_name: str
    samples: int
    latest_state: str
    latest_burn_rate: float
    min_burn_rate: float
    max_burn_rate: float
    avg_burn_rate: float
    direction: str  # "improving" | "worsening" | "stable"
    series: list[SLOSnapshot] = Field(default_factory=list)


class SLOHistory:
    def __init__(self, max_per_slo: int = 100) -> None:
        self._series: dict[str, deque[SLOSnapshot]] = {}
        self._max = max_per_slo

    def record(self, budgets: list[ErrorBudget]) -> None:
        for b in budgets:
            snap = SLOSnapshot(
                slo_id=b.slo_id, slo_name=b.slo_name, state=b.state.value,
                burn_rate=b.burn_rate, consumed_fraction=b.consumed_fraction,
            )
            dq = self._series.setdefault(b.slo_id, deque(maxlen=self._max))
            dq.append(snap)

    def trend(self, slo_id: str) -> SLOTrend | None:
        dq = self._series.get(slo_id)
        if not dq:
            return None
        series = list(dq)
        rates = [s.burn_rate for s in series]
        direction = "stable"
        if len(rates) >= 2:
            if rates[-1] > rates[0] * 1.05:
                direction = "worsening"
            elif rates[-1] < rates[0] * 0.95:
                direction = "improving"
        return SLOTrend(
            slo_id=slo_id, slo_name=series[-1].slo_name, samples=len(series),
            latest_state=series[-1].state, latest_burn_rate=series[-1].burn_rate,
            min_burn_rate=min(rates), max_burn_rate=max(rates),
            avg_burn_rate=round(sum(rates) / len(rates), 4), direction=direction,
            series=series,
        )

    def all_trends(self) -> list[SLOTrend]:
        out = []
        for sid in self._series:
            t = self.trend(sid)
            if t is not None:
                out.append(t)
        return out
