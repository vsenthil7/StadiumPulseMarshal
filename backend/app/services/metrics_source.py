"""Metrics-backend adapter → MetricsHistory.

The burn engine needs per-window error rates from real samples. This module
provides a ``MetricsSource`` that yields a time series of error-rate samples per
SLO, and a backfill that loads them into ``MetricsHistory`` so the multi-window
burn evaluation runs on genuine windowed data rather than a single point.

Two implementations:
- ``SyntheticMetricsSource`` — deterministic per-SLO series (demo/mock), shaped so
  some SLOs show a recent spike (fast burn), some a sustained elevated rate
  (slow burn), some clean.
- ``DynatraceMetricsSource`` — pulls a metric timeseries from the Dynatrace
  Metrics v2 API and converts it to error-rate samples; falls back to synthetic
  on any error so the engine never hard-fails.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.slo import SLO

log = get_logger(__name__)


@dataclass
class ErrorSample:
    at: float          # epoch seconds
    error_rate: float  # 0..1
    weight: float = 1.0


class MetricsSource(Protocol):
    async def error_series(self, slo: SLO, lookback_hours: float) -> list[ErrorSample]:
        ...


class SyntheticMetricsSource:
    """Deterministic per-SLO error series for mock mode.

    Buckets by SLO id (matching the synthetic_measurement spread):
    - fast: clean for most of the window, sharp recent spike (both windows hot)
    - slow: sustained mild elevation across the whole window
    - healthy: well under budget throughout
    - recovered: hot early in the window, clean recently (long hot, short cold)
    """

    def __init__(self, sample_interval_minutes: float = 5.0) -> None:
        self._interval = sample_interval_minutes * 60.0

    async def error_series(self, slo: SLO, lookback_hours: float) -> list[ErrorSample]:
        now = time.time()
        allowed = slo.allowed_error_fraction or 0.001
        bucket = sum(ord(c) for c in slo.id) % 4
        n = max(1, int((lookback_hours * 3600) / self._interval))
        samples: list[ErrorSample] = []
        for i in range(n):
            # i=0 oldest … i=n-1 newest
            age_frac = 1.0 - (i / max(1, n - 1))  # 1.0 oldest → 0.0 newest
            recent = age_frac < (5 / 60) / lookback_hours if lookback_hours else False
            if bucket == 0:      # fast: recent spike
                rate = allowed * (15.0 if i >= n - 2 else 0.3)
            elif bucket == 1:    # slow: sustained mild elevation
                rate = allowed * 3.5
            elif bucket == 2:    # healthy
                rate = allowed * 0.3
            else:                # recovered: hot early, clean recently
                rate = allowed * (8.0 if age_frac > 0.5 else 0.0)
            at = now - (n - 1 - i) * self._interval
            samples.append(ErrorSample(at=at, error_rate=min(1.0, rate)))
        return samples


class DynatraceMetricsSource:
    """Pulls an error-rate timeseries from Dynatrace Metrics v2.

    Maps the SLO's service entity to a metric selector and converts the returned
    datapoints to error-rate samples. On any API/parse error it falls back to the
    synthetic source so burn evaluation degrades gracefully.
    """

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None,
                 fallback: MetricsSource | None = None) -> None:
        self._settings = settings
        self._http = http
        self._fallback = fallback or SyntheticMetricsSource()

    async def error_series(self, slo: SLO, lookback_hours: float) -> list[ErrorSample]:
        base = (self._settings.dt_tenant_url or "").rstrip("/")
        token = self._settings.dt_api_token
        if not base or not token:
            return await self._fallback.error_series(slo, lookback_hours)
        owns = self._http is None
        http = self._http or httpx.AsyncClient(timeout=5.0)
        try:
            # Error-rate metric for the SLO's service entity (representative
            # selector; a real mapping would be configured per SLI).
            url = f"{base}/api/v2/metrics/query"
            params = {
                "metricSelector": (
                    f"builtin:service.errors.total.rate:filter("
                    f"eq(dt.entity.service,{slo.service_id}))"
                ),
                "from": f"now-{int(lookback_hours)}h",
                "resolution": "5m",
            }
            r = await http.get(
                url, params=params,
                headers={"Authorization": f"Api-Token {token}"},
            )
            r.raise_for_status()
            data = r.json()
            samples = _parse_dt_timeseries(data)
            if not samples:
                return await self._fallback.error_series(slo, lookback_hours)
            return samples
        except Exception as exc:  # noqa: BLE001 - optional source, never fatal
            log.warning("Dynatrace metrics fetch failed; using synthetic: %s", exc)
            return await self._fallback.error_series(slo, lookback_hours)
        finally:
            if owns:
                await http.aclose()


def _parse_dt_timeseries(data: dict) -> list[ErrorSample]:
    """Convert a Dynatrace Metrics v2 result to error-rate samples.

    Expects ``result[0].data[0]`` with parallel ``timestamps`` (ms) and
    ``values`` (rate as a percentage 0..100 or fraction 0..1).
    """
    out: list[ErrorSample] = []
    try:
        series = data["result"][0]["data"][0]
        timestamps = series.get("timestamps", [])
        values = series.get("values", [])
        for ts, val in zip(timestamps, values):
            if val is None:
                continue
            rate = float(val)
            if rate > 1.0:  # percentage → fraction
                rate /= 100.0
            out.append(ErrorSample(at=ts / 1000.0, error_rate=min(1.0, max(0.0, rate))))
    except (KeyError, IndexError, TypeError, ValueError):
        return []
    return out


def build_metrics_source(settings: Settings) -> MetricsSource:
    """Dynatrace metrics source when a tenant is configured, else synthetic."""
    if settings.dt_tenant_url and settings.dt_api_token:
        return DynatraceMetricsSource(settings)
    return SyntheticMetricsSource()


async def backfill_history(source: MetricsSource, slos: list[SLO], history,
                           lookback_hours: float = 6.0) -> int:
    """Load each SLO's error series from ``source`` into ``history``.

    Returns the number of samples recorded. Used to prime MetricsHistory so the
    burn engine's multi-window evaluation has real per-window data.
    """
    count = 0
    for slo in slos:
        try:
            samples = await source.error_series(slo, lookback_hours)
        except Exception:  # noqa: BLE001
            samples = []
        for s in samples:
            history.record(slo.id, s.error_rate, weight=s.weight, at=s.at)
            count += 1
    return count
