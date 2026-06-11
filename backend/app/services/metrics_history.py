"""Per-SLO metrics history for multi-window burn-rate computation.

Burn-rate alerting needs the error rate over two different trailing windows (a
long and a short one) so a tier fires only when both agree. This service records
per-SLO error-rate samples with timestamps in an in-memory ring buffer and
aggregates the error rate over an arbitrary trailing window. Swappable for a
real time-series backend (Prometheus/Dynatrace) behind the same interface — the
burn engine only needs ``error_rate_over(slo_id, hours)``.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class _Sample:
    at: float          # epoch seconds
    error_rate: float  # 0..1 observed in the small slice this sample covers
    weight: float      # relative weight (e.g. event volume); default 1


class MetricsHistory:
    def __init__(self, max_per_slo: int = 2000) -> None:
        self._series: dict[str, deque[_Sample]] = {}
        self._max = max_per_slo

    def record(self, slo_id: str, error_rate: float, weight: float = 1.0,
               at: float | None = None) -> None:
        dq = self._series.setdefault(slo_id, deque(maxlen=self._max))
        dq.append(_Sample(at=at or time.time(), error_rate=max(0.0, error_rate),
                          weight=max(0.0, weight)))

    def error_rate_over(self, slo_id: str, hours: float,
                        now: float | None = None) -> float | None:
        """Weighted mean error rate over the trailing ``hours`` window.

        Returns None when there are no samples in the window (caller decides how
        to treat absence — typically "no burn").
        """
        dq = self._series.get(slo_id)
        if not dq:
            return None
        now = now or time.time()
        cutoff = now - hours * 3600
        num = 0.0
        den = 0.0
        for s in dq:
            if s.at >= cutoff:
                num += s.error_rate * s.weight
                den += s.weight
        if den == 0:
            return None
        return num / den

    def has_samples(self, slo_id: str) -> bool:
        return bool(self._series.get(slo_id))

    def sample_count(self, slo_id: str) -> int:
        return len(self._series.get(slo_id, ()))
