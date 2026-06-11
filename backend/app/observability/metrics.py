"""Minimal in-process metrics registry with Prometheus text exposition.

Implements counters and histograms sufficient for service self-observability
without pulling a heavy client library. Thread-safety is not required for the
single-process async server; updates are cheap dict operations.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

# Default histogram buckets (seconds) for request latency.
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


def _fmt_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


@dataclass
class Counter:
    name: str
    help: str
    _values: dict[tuple, float] = field(default_factory=dict)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        return self._values.get(tuple(sorted(labels.items())), 0.0)

    def expose(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        if not self._values:
            lines.append(f"{self.name} 0")
        for key, val in self._values.items():
            lines.append(f"{self.name}{_fmt_labels(dict(key))} {val}")
        return lines


@dataclass
class Histogram:
    name: str
    help: str
    buckets: tuple = DEFAULT_BUCKETS
    _counts: dict[tuple, list] = field(default_factory=dict)
    _sums: dict[tuple, float] = field(default_factory=dict)

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        if key not in self._counts:
            self._counts[key] = [0] * (len(self.buckets) + 1)
            self._sums[key] = 0.0
        self._sums[key] += value
        placed = False
        for i, b in enumerate(self.buckets):
            if value <= b:
                self._counts[key][i] += 1
                placed = True
                break
        if not placed:
            self._counts[key][-1] += 1

    def expose(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for key, counts in self._counts.items():
            labels = dict(key)
            cumulative = 0
            for i, b in enumerate(self.buckets):
                cumulative += counts[i]
                le = {**labels, "le": str(b)}
                lines.append(f"{self.name}_bucket{_fmt_labels(le)} {cumulative}")
            cumulative += counts[-1]
            le_inf = {**labels, "le": "+Inf"}
            lines.append(f"{self.name}_bucket{_fmt_labels(le_inf)} {cumulative}")
            lines.append(f"{self.name}_sum{_fmt_labels(labels)} {self._sums[key]}")
            lines.append(f"{self.name}_count{_fmt_labels(labels)} {cumulative}")
        return lines


class MetricsRegistry:
    """Holds the application's metrics and renders Prometheus text."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests_total = Counter(
            "stadiumpulse_requests_total", "Total HTTP requests."
        )
        self.request_duration = Histogram(
            "stadiumpulse_request_duration_seconds", "Request duration."
        )
        self.incidents_created = Counter(
            "stadiumpulse_incidents_created_total", "Incidents created."
        )
        self.remediations_decided = Counter(
            "stadiumpulse_remediations_decided_total", "Remediation decisions."
        )
        self.events_published = Counter(
            "stadiumpulse_events_published_total", "Domain events published."
        )
        self.webhook_deliveries = Counter(
            "stadiumpulse_webhook_deliveries_total", "Webhook delivery attempts."
        )

    def observe_request(self, method: str, path: str, status: int, dur: float) -> None:
        with self._lock:
            self.requests_total.inc(method=method, status=str(status))
            self.request_duration.observe(dur, method=method)

    def render(self) -> str:
        with self._lock:
            blocks = [
                self.requests_total,
                self.request_duration,
                self.incidents_created,
                self.remediations_decided,
                self.events_published,
                self.webhook_deliveries,
            ]
            lines: list[str] = []
            for m in blocks:
                lines.extend(m.expose())
            return "\n".join(lines) + "\n"


_registry: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
    return _registry


def reset_metrics() -> None:
    """Test helper: drop the singleton so a fresh registry is created."""
    global _registry
    _registry = None
