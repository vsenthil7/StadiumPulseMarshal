"""Per-window error-rate aggregation + window-driven burn classification."""
from __future__ import annotations

import time

import pytest

from app.models.slo import SLO, SLI, SLIKind, ErrorBudget, BurnState, BurnSeverity
from app.services.metrics_history import MetricsHistory
from app.services.burn_alerts import evaluate_burn_alerts


def _slo(target=0.99):
    return SLO(id="SLO-X", name="API", service_id="SVC-PAYMENTS",
               sli=SLI(kind=SLIKind.AVAILABILITY, key="a", unit="ratio",
                       entity_id="SVC-PAYMENTS"),
               target=target, window_hours=24)


def _budget(achieved=0.999):
    return ErrorBudget(slo_id="SLO-X", slo_name="API", target=0.99,
                       achieved=achieved, consumed_fraction=0.1,
                       remaining_fraction=0.9, burn_rate=1.0,
                       state=BurnState.HEALTHY)


def test_window_aggregation_trailing():
    m = MetricsHistory()
    now = time.time()
    # old high-error sample (2h ago) + recent low-error samples
    m.record("SLO-X", 0.50, at=now - 2 * 3600)
    m.record("SLO-X", 0.01, at=now - 60)
    m.record("SLO-X", 0.01, at=now - 30)
    # 5-minute window only sees the recent low-error samples
    short = m.error_rate_over("SLO-X", 5 / 60, now=now)
    assert short is not None and short < 0.05
    # 6-hour window includes the old spike → higher
    long = m.error_rate_over("SLO-X", 6.0, now=now)
    assert long is not None and long > short


def test_no_samples_in_window_returns_none():
    m = MetricsHistory()
    m.record("SLO-X", 0.5, at=time.time() - 10 * 3600)
    assert m.error_rate_over("SLO-X", 1.0) is None  # nothing in last hour


def test_burn_uses_real_windows_fast_pages():
    # Sustained high error in BOTH short and long windows → fast page.
    m = MetricsHistory()
    now = time.time()
    for dt in (10, 60, 300, 1800, 3000):  # spread across last ~50min
        m.record("SLO-X", 0.25, at=now - dt)
    alerts = evaluate_burn_alerts([_slo()], [_budget()], {"SLO-X": "venue_arena_north"},
                                  metrics=m)
    assert len(alerts) == 1
    assert alerts[0].severity == BurnSeverity.PAGE


def test_burn_short_window_cold_no_page():
    # High error long ago, but the SHORT window is clean → no page (multiwindow
    # guard against alerting on an already-recovered incident).
    m = MetricsHistory()
    now = time.time()
    m.record("SLO-X", 0.40, at=now - 5 * 3600)   # in 6h window
    m.record("SLO-X", 0.0, at=now - 30)          # short window clean
    m.record("SLO-X", 0.0, at=now - 10)
    alerts = evaluate_burn_alerts([_slo()], [_budget()], {}, metrics=m)
    # medium tier (6h/30m): long hot but short cold → must not fire
    pages = [a for a in alerts if a.severity == BurnSeverity.PAGE]
    assert pages == []


def test_falls_back_to_budget_without_samples():
    m = MetricsHistory()  # empty
    # budget shows 20% error → fast burn via fallback path
    alerts = evaluate_burn_alerts([_slo()], [_budget(achieved=0.80)], {}, metrics=m)
    assert len(alerts) == 1 and alerts[0].severity == BurnSeverity.PAGE
