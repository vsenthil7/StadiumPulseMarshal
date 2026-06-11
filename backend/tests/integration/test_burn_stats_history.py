"""Burn-events pagination/CSV + suppression analytics."""
from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _resp(c):
    return c.post("/api/v1/auth/login",
                  json={"email": "responder@arena-north.demo", "password": PW}).json()["token"]


def _seed(c, h):
    a = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
    if not a:
        return None
    x = a[0]
    c.post(f"/api/v1/slo/burn-alerts/{x['slo_id']}/ack",
           json={"severity": x["severity"]}, headers=h)
    c.post(f"/api/v1/slo/burn-alerts/{x['slo_id']}/silence",
           json={"severity": x["severity"], "minutes": 15}, headers=h)
    return x


def test_burn_events_pagination_and_csv():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        if not _seed(c, h):
            return
        page = c.get("/api/v1/slo/burn-events?limit=1&offset=0", headers=h).json()
        assert page["limit"] == 1 and "total" in page and len(page["events"]) <= 1
        csv = c.get("/api/v1/slo/burn-events?fmt=csv", headers=h)
        assert csv.status_code == 200 and "text/csv" in csv.headers["content-type"]
        assert "timestamp,actor,action,target" in csv.text


def test_burn_stats_counts_and_ratio():
    with TestClient(create_app()) as c:
        h = {"Authorization": f"Bearer {_resp(c)}"}
        if not _seed(c, h):
            return
        stats = c.get("/api/v1/slo/burn-stats", headers=h).json()
        assert stats["counts"]["ack"] >= 1
        assert stats["counts"]["silence"] >= 1
        assert 0.0 <= stats["suppression_ratio"] <= 1.0
        assert "most_silenced" in stats
        assert stats["active_silences"] >= 1
