"""Burn-trend buckets + analytics burn suppression KPIs."""
from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _resp(c):
    return c.post("/api/v1/auth/login",
                  json={"email": "responder@arena-north.demo", "password": PW}).json()["token"]


def test_burn_trend_buckets_shape():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        r = c.get("/api/v1/slo/burn-trend?hours=24&buckets=12", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert len(body["buckets"]) == 12
        assert all(set(b) >= {"ack", "silence", "start_epoch"} for b in body["buckets"])


def test_burn_trend_counts_recent_action():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not alerts:
            return
        a = alerts[0]
        c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/silence",
               json={"severity": a["severity"], "minutes": 10}, headers=h)
        body = c.get("/api/v1/slo/burn-trend?hours=24&buckets=6", headers=h).json()
        # the most recent bucket should carry the silence
        assert sum(b["silence"] for b in body["buckets"]) >= 1


def test_analytics_summary_has_burn_kpis():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if alerts:
            a = alerts[0]
            c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/silence",
                   json={"severity": a["severity"], "minutes": 10}, headers=h)
        s = c.get("/api/v1/analytics", headers=h).json()["summary"]
        assert "burn_active_silences" in s
        assert "burn_suppression_ratio" in s
        assert "burn_page_alerts" in s and "burn_ticket_alerts" in s
