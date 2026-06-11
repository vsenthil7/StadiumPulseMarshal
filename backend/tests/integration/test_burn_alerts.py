"""Multi-window burn-rate alerting: tiering + scoped endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.slo import SLO, SLI, SLIKind, BurnSeverity, ErrorBudget, BurnState
from app.services.burn_alerts import classify_burn, evaluate_burn_alerts

PW = "MatchdayDemo123!"


def _slo(target=0.99, window=24):
    return SLO(
        id="SLO-X", name="API availability", service_id="SVC-PAYMENTS",
        sli=SLI(kind=SLIKind.AVAILABILITY, key="avail", unit="ratio",
                entity_id="SVC-PAYMENTS"),
        target=target, window_hours=window,
    )


def test_fast_burn_pages():
    slo = _slo(target=0.99)  # 1% budget
    # 20% error rate → burn rate 20x → above 14.4x fast tier → PAGE
    alert = classify_burn(slo, long_error_rate=0.20)
    assert alert is not None and alert.severity == BurnSeverity.PAGE
    assert alert.burn_rate >= 14.4


def test_slow_burn_tickets():
    slo = _slo(target=0.99)  # 1% budget
    # 3.5% error → 3.5x burn → between 3x (slow) and 6x (medium) → TICKET
    alert = classify_burn(slo, long_error_rate=0.035)
    assert alert is not None and alert.severity == BurnSeverity.TICKET


def test_no_burn_is_silent():
    slo = _slo(target=0.99)
    # 0.5% error → 0.5x burn → below the 1x trickle tier → no alert
    assert classify_burn(slo, long_error_rate=0.005) is None


def test_multiwindow_requires_both_windows():
    slo = _slo(target=0.99)
    # long window hot (20x) but short window cold (0) → no page (guards flapping)
    assert classify_burn(slo, long_error_rate=0.20, short_error_rate=0.0) is None


def test_evaluate_maps_budgets_to_alerts():
    slo = _slo(target=0.99)
    budget = ErrorBudget(
        slo_id="SLO-X", slo_name="API availability", target=0.99,
        achieved=0.80, consumed_fraction=1.0, remaining_fraction=0.0,
        burn_rate=20.0, state=BurnState.FAST_BURN,
    )
    alerts = evaluate_burn_alerts([slo], [budget], {"SLO-X": "venue_arena_north"})
    assert len(alerts) == 1
    assert alerts[0].severity == BurnSeverity.PAGE
    assert alerts[0].venue_id == "venue_arena_north"


def test_burn_alerts_endpoint_scoped():
    with TestClient(create_app()) as c:
        sre = c.post("/api/v1/auth/login",
                     json={"email": "sre@stadiumpulse.demo", "password": PW}).json()["token"]
        r = c.get("/api/v1/slo/burn-alerts",
                  headers={"Authorization": f"Bearer {sre}"})
        assert r.status_code == 200
        body = r.json()
        assert "alerts" in body and "page_count" in body and "ticket_count" in body
        # operator scoped to a venue only sees that venue's alerts
        op = c.post("/api/v1/auth/login",
                    json={"email": "operator@olympic-park.demo", "password": PW}).json()["token"]
        ro = c.get("/api/v1/slo/burn-alerts",
                   headers={"Authorization": f"Bearer {op}"}).json()
        assert all(a["venue_id"] in (None, "venue_olympic_park") for a in ro["alerts"])
