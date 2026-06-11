"""Burn-alert acknowledge / silence workflow."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.burn_ack_store import BurnAckStore

PW = "MatchdayDemo123!"


def _login(c, email):
    return c.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["token"]


# ── store unit ──────────────────────────────────────────────────────────────
def test_store_ack_and_silence_expiry():
    s = BurnAckStore()
    s.acknowledge("SLO-X", "page", "alice", "looking")
    assert s.ack_for("SLO-X", "page").acked_by == "alice"
    # silence 0.001 min ≈ 0.06s then expires
    s.silence("SLO-X", "page", minutes=0.001, by="alice")
    assert s.is_silenced("SLO-X", "page") is True
    time.sleep(0.1)
    assert s.is_silenced("SLO-X", "page") is False


# ── endpoint RBAC + behaviour ───────────────────────────────────────────────
def test_ack_requires_responder():
    with TestClient(create_app()) as c:
        viewer = _login(c, "viewer@arena-north.demo")
        r = c.post("/api/v1/slo/burn-alerts/SLO-X/ack",
                   json={"severity": "ticket"},
                   headers={"Authorization": f"Bearer {viewer}"})
        assert r.status_code == 403


def test_responder_can_ack_and_it_shows_on_alerts():
    with TestClient(create_app()) as c:
        # responder role: assume an operator lacks it, a responder has it.
        tok = _login(c, "responder@arena-north.demo")
        h = {"Authorization": f"Bearer {tok}"}
        # find a current alert to ack
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not alerts:
            pytest.skip("no burn alerts in scenario")
        a = alerts[0]
        r = c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/ack",
                   json={"severity": a["severity"], "note": "on it"}, headers=h)
        assert r.status_code == 200 and r.json()["acknowledged"]
        # re-list: that alert is now acknowledged
        again = c.get("/api/v1/slo/burn-alerts", headers=h).json()
        match = [x for x in again["alerts"]
                 if x["slo_id"] == a["slo_id"] and x["severity"] == a["severity"]]
        assert match and match[0]["acknowledged"] is True
        assert again["acked_count"] >= 1


def test_silence_suppresses_and_marks():
    with TestClient(create_app()) as c:
        tok = _login(c, "responder@arena-north.demo")
        h = {"Authorization": f"Bearer {tok}"}
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not alerts:
            pytest.skip("no burn alerts")
        a = alerts[0]
        c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/silence",
               json={"severity": a["severity"], "minutes": 30}, headers=h)
        again = c.get("/api/v1/slo/burn-alerts", headers=h).json()
        match = [x for x in again["alerts"]
                 if x["slo_id"] == a["slo_id"] and x["severity"] == a["severity"]]
        assert match and match[0]["silenced"] is True
        assert again["silenced_count"] >= 1


def test_unack_clears_and_audited():
    with TestClient(create_app()) as c:
        tok = _login(c, "responder@arena-north.demo")
        h = {"Authorization": f"Bearer {tok}"}
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not alerts:
            pytest.skip("no burn alerts")
        a = alerts[0]
        c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/ack",
               json={"severity": a["severity"]}, headers=h)
        # un-ack
        r = c.request("DELETE", f"/api/v1/slo/burn-alerts/{a['slo_id']}/ack",
                      params={"severity": a["severity"]}, headers=h)
        assert r.status_code == 200 and r.json()["cleared"] is True
        again = c.get("/api/v1/slo/burn-alerts", headers=h).json()
        match = [x for x in again["alerts"]
                 if x["slo_id"] == a["slo_id"] and x["severity"] == a["severity"]]
        assert match and match[0]["acknowledged"] is False


def test_burn_events_history():
    with TestClient(create_app()) as c:
        tok = _login(c, "responder@arena-north.demo")
        h = {"Authorization": f"Bearer {tok}"}
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not alerts:
            pytest.skip("no burn alerts")
        a = alerts[0]
        c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/ack",
               json={"severity": a["severity"], "note": "hist"}, headers=h)
        ev = c.get("/api/v1/slo/burn-events", headers=h).json()
        assert ev["total"] >= 1
        assert any(e["action"] == "burn.ack" for e in ev["events"])
        # filter
        only = c.get("/api/v1/slo/burn-events?action=burn.ack", headers=h).json()
        assert all(e["action"] == "burn.ack" for e in only["events"])


def test_burn_events_requires_responder():
    with TestClient(create_app()) as c:
        v = _login(c, "viewer@arena-north.demo")
        r = c.get("/api/v1/slo/burn-events", headers={"Authorization": f"Bearer {v}"})
        assert r.status_code == 403


def test_oncall_ack_state_present():
    with TestClient(create_app()) as c:
        tok = _login(c, "responder@arena-north.demo")
        h = {"Authorization": f"Bearer {tok}"}
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if alerts:
            a = alerts[0]
            c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/silence",
                   json={"severity": a["severity"], "minutes": 15}, headers=h)
        oc = c.get("/api/v1/oncall", headers=h).json()
        assert "ack_state" in oc and "acks" in oc["ack_state"] and "silences" in oc["ack_state"]
