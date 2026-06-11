"""Cost analytics, change events, fleet command center."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _h(c, email="responder@arena-north.demo"):
    tok = c.post("/api/v1/auth/login",
                 json={"email": email, "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


# ── cost ────────────────────────────────────────────────────────────────────
def test_cost_analytics_summary():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/cost-analytics", headers=_h(c, "viewer@arena-north.demo"))
        assert r.status_code == 200
        body = r.json()
        assert body["total_monthly_cost_usd"] > 0
        assert len(body["services"]) >= 3
        # ticketing/concessions are low-util → downsize candidates
        assert body["downsize_candidates"] >= 1


def test_cost_rightsizing_flags():
    with TestClient(create_app()) as c:
        body = c.get("/api/v1/cost-analytics", headers=_h(c)).json()
        flags = {s["service_id"]: s["rightsizing"] for s in body["services"]}
        assert flags["SVC-STREAMING"] == "upsize"
        assert flags["SVC-CONCESSIONS"] == "downsize"


# ── change events ─────────────────────────────────────────────────────────��─
def test_record_and_list_change_event():
    with TestClient(create_app()) as c:
        h = _h(c)
        ev = c.post("/api/v1/change-events",
                    json={"title": "Deploy v1.2", "service_id": "SVC-PAYMENTS"},
                    headers=h).json()
        assert ev["id"].startswith("CHG-")
        lst = c.get("/api/v1/change-events?service_id=SVC-PAYMENTS", headers=h).json()
        assert any(e["id"] == ev["id"] for e in lst["events"])


def test_link_change_event_to_incident():
    with TestClient(create_app()) as c:
        h = _h(c)
        ev = c.post("/api/v1/change-events", json={"title": "Config change"},
                    headers=h).json()
        linked = c.post(f"/api/v1/change-events/{ev['id']}/link/INC-9", headers=h).json()
        assert "INC-9" in linked["linked_incident_ids"]


def test_correlate_change_events():
    with TestClient(create_app()) as c:
        h = _h(c)
        c.post("/api/v1/change-events",
               json={"title": "Recent deploy", "service_id": "SVC-PAYMENTS"}, headers=h)
        now = datetime.now(timezone.utc).isoformat()
        r = c.get(f"/api/v1/change-events/correlate?incident_time={now}"
                  f"&service_id=SVC-PAYMENTS", headers=h)
        assert r.status_code == 200
        assert len(r.json()["events"]) >= 1


# ── fleet ─────────────────────────────────────────────────────────────────────
def test_fleet_summary():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/fleet", headers=_h(c, "sre@stadiumpulse.demo"))
        assert r.status_code == 200
        body = r.json()
        # either per-venue rows or a global summary fallback
        assert "venues" in body
