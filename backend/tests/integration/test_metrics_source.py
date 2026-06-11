"""Metrics-backend adapter: synthetic series, DT parse, fallback, backfill."""
from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.models.slo import SLO, SLI, SLIKind
from app.services.metrics_history import MetricsHistory
from app.services.metrics_source import (
    DynatraceMetricsSource,
    SyntheticMetricsSource,
    _parse_dt_timeseries,
    backfill_history,
    build_metrics_source,
)


def _slo(sid="SLO-PAY"):
    return SLO(id=sid, name="API", service_id="SVC-PAYMENTS",
               sli=SLI(kind=SLIKind.AVAILABILITY, key="a", unit="ratio",
                       entity_id="SVC-PAYMENTS"),
               target=0.99, window_hours=24)


@pytest.mark.asyncio
async def test_synthetic_series_has_samples_across_window():
    src = SyntheticMetricsSource(sample_interval_minutes=5)
    series = await src.error_series(_slo(), lookback_hours=6)
    assert len(series) > 10
    assert all(0.0 <= s.error_rate <= 1.0 for s in series)
    # newest timestamp is most recent
    assert series[-1].at >= series[0].at


@pytest.mark.asyncio
async def test_backfill_populates_history_windows():
    src = SyntheticMetricsSource()
    hist = MetricsHistory()
    slos = [_slo("SLO-A"), _slo("SLO-B")]
    n = await backfill_history(src, slos, hist, lookback_hours=6)
    assert n > 0
    # each SLO now has a queryable trailing-window rate
    for s in slos:
        assert hist.has_samples(s.id)
        assert hist.error_rate_over(s.id, 6.0) is not None


def test_build_source_synthetic_without_tenant():
    assert isinstance(build_metrics_source(Settings()), SyntheticMetricsSource)


def test_build_source_dynatrace_with_tenant():
    s = build_metrics_source(Settings(dt_tenant_url="https://x.live.dynatrace.com",
                                      dt_api_token="dt0c01.x"))
    assert isinstance(s, DynatraceMetricsSource)


def test_parse_dt_timeseries_percentage_and_fraction():
    data = {"result": [{"data": [{
        "timestamps": [1700000000000, 1700000300000],
        "values": [5.0, 0.02],  # 5% then 0.02 fraction
    }]}]}
    samples = _parse_dt_timeseries(data)
    assert len(samples) == 2
    assert abs(samples[0].error_rate - 0.05) < 1e-9
    assert abs(samples[1].error_rate - 0.02) < 1e-9


@pytest.mark.asyncio
async def test_dynatrace_source_pulls_then_parses():
    settings = Settings(dt_tenant_url="https://x.live.dynatrace.com",
                        dt_api_token="dt0c01.x")

    def handler(req):
        assert "metrics/query" in str(req.url)
        return httpx.Response(200, json={"result": [{"data": [{
            "timestamps": [1700000000000], "values": [10.0]}]}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        src = DynatraceMetricsSource(settings, http=http)
        series = await src.error_series(_slo(), lookback_hours=1)
        assert series and abs(series[0].error_rate - 0.10) < 1e-9
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_dynatrace_source_falls_back_on_error():
    settings = Settings(dt_tenant_url="https://x.live.dynatrace.com",
                        dt_api_token="dt0c01.x")

    def handler(req):
        return httpx.Response(500, json={"error": "boom"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        src = DynatraceMetricsSource(settings, http=http)
        series = await src.error_series(_slo(), lookback_hours=6)
        # falls back to synthetic → still returns samples
        assert len(series) > 0
    finally:
        await http.aclose()
