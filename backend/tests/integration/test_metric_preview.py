"""Metric-selector preview endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _tok(c, email="sre@stadiumpulse.demo"):
    return c.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["token"]


def test_metric_preview_returns_selector_and_series():
    with TestClient(create_app()) as c:
        tok = _tok(c)
        h = {"Authorization": f"Bearer {tok}"}
        slos = c.get("/api/v1/slo", headers=h).json()["budgets"]
        assert slos
        slo_id = slos[0]["slo_id"]
        r = c.get(f"/api/v1/slo/{slo_id}/metric-preview", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["metric_selector"]  # a resolved selector string
        assert "window_error_rates" in body
        assert set(body["window_error_rates"].keys()) == {"5m", "1h", "6h"}
        assert body["sample_count"] >= 1


def test_metric_preview_unknown_slo_404():
    with TestClient(create_app()) as c:
        tok = _tok(c)
        r = c.get("/api/v1/slo/NOPE/metric-preview",
                  headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 404
