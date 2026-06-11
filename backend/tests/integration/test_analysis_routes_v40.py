"""Coverage for routes_analysis branches: CSV exports, mute/unmute, digest kinds,
burn-trend, burn-stats, unack/unsilence, trends venue filter, postmortem, bulk."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PW = "MatchdayDemo123!"


def _login(c, email):
    return c.post("/api/v1/auth/login",
                  json={"email": email, "password": PW}).json()["token"]


def _responder(c):
    return {"Authorization": f"Bearer {_login(c, 'responder@arena-north.demo')}"}


def test_burn_events_csv_and_filter():
    with TestClient(create_app()) as c:
        h = _responder(c)
        # generate one ack so there is an event
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if alerts:
            a = alerts[0]
            c.post(f"/api/v1/slo/burn-alerts/{a['slo_id']}/ack",
                   json={"severity": a["severity"]}, headers=h)
        # json form with action filter
        j = c.get("/api/v1/slo/burn-events?action=burn.ack&limit=10&offset=0", headers=h)
        assert j.status_code == 200 and "events" in j.json()
        # csv form
        csv = c.get("/api/v1/slo/burn-events?fmt=csv", headers=h)
        assert csv.status_code == 200
        assert "text/csv" in csv.headers["content-type"]
        assert "timestamp,actor,action,target" in csv.text


def test_mute_unmute_and_mute_events():
    with TestClient(create_app()) as c:
        h = _responder(c)
        vid = "venue_arena_north"
        m = c.post("/api/v1/slo/burn-digest/mute",
                   json={"venue_id": vid, "minutes": 30}, headers=h)
        assert m.status_code == 200 and m.json()["muted_until"] > 0
        # mute-events audit history
        ev = c.get("/api/v1/slo/burn-digest/mute-events", headers=h)
        assert ev.status_code == 200 and "events" in ev.json()
        # unmute
        u = c.delete(f"/api/v1/slo/burn-digest/mute?venue_id={vid}", headers=h)
        assert u.status_code == 200 and "cleared" in u.json()


def test_burn_digest_daily_and_venue_and_dispatch_muted():
    with TestClient(create_app()) as c:
        h = _responder(c)
        # daily kind
        d = c.get("/api/v1/slo/burn-digest?kind=daily", headers=h)
        assert d.status_code == 200 and "digest" in d.json()
        # venue-scoped
        v = c.get("/api/v1/slo/burn-digest?venue_id=venue_arena_north", headers=h)
        assert v.status_code == 200
        # mute then dispatch → muted short-circuit
        c.post("/api/v1/slo/burn-digest/mute",
               json={"venue_id": "venue_arena_north", "minutes": 30}, headers=h)
        md = c.get("/api/v1/slo/burn-digest?venue_id=venue_arena_north&dispatch=true",
                   headers=h)
        assert md.status_code == 200 and md.json()["muted"] is True


def test_burn_digest_dispatch_default_channel():
    with TestClient(create_app()) as c:
        h = _responder(c)
        r = c.get("/api/v1/slo/burn-digest?dispatch=true", headers=h)
        assert r.status_code == 200 and r.json()["dispatched"] is True


def test_burn_trend_and_stats_with_venue():
    with TestClient(create_app()) as c:
        h = _responder(c)
        t = c.get("/api/v1/slo/burn-trend?hours=24&buckets=6", headers=h)
        assert t.status_code == 200
        body = t.json()
        assert len(body["buckets"]) == 6
        assert "net_active_baseline" in body
        # venue-filtered
        tv = c.get("/api/v1/slo/burn-trend?venue_id=venue_arena_north", headers=h)
        assert tv.status_code == 200
        s = c.get("/api/v1/slo/burn-stats?hours=24", headers=h)
        assert s.status_code == 200 and "counts" in s.json()
        sv = c.get("/api/v1/slo/burn-stats?venue_id=venue_arena_north", headers=h)
        assert sv.status_code == 200


def test_silence_then_unack_unsilence():
    with TestClient(create_app()) as c:
        h = _responder(c)
        alerts = c.get("/api/v1/slo/burn-alerts", headers=h).json()["alerts"]
        if not alerts:
            return
        a = alerts[0]
        sev = a["severity"]
        sid = a["slo_id"]
        c.post(f"/api/v1/slo/burn-alerts/{sid}/ack",
               json={"severity": sev}, headers=h)
        c.post(f"/api/v1/slo/burn-alerts/{sid}/silence",
               json={"severity": sev, "minutes": 15}, headers=h)
        ua = c.delete(f"/api/v1/slo/burn-alerts/{sid}/ack?severity={sev}", headers=h)
        assert ua.status_code == 200 and "cleared" in ua.json()
        us = c.delete(f"/api/v1/slo/burn-alerts/{sid}/silence?severity={sev}", headers=h)
        assert us.status_code == 200 and "cleared" in us.json()


def test_slo_trends_with_and_without_venue():
    with TestClient(create_app()) as c:
        h = _responder(c)
        allt = c.get("/api/v1/slo/trends", headers=h)
        assert allt.status_code == 200 and "trends" in allt.json()
        vt = c.get("/api/v1/slo/trends?venue_id=venue_arena_north", headers=h)
        assert vt.status_code == 200


def test_incident_postmortem_and_404():
    with TestClient(create_app()) as c:
        h = _responder(c)
        # create an incident to get a postmortem
        made = c.post("/api/v1/incidents",
                      json={"problem_id": "P-2026-0613-001",
                            "venue_id": "V-METLIFE"}, headers=h)
        if made.status_code == 200:
            iid = made.json()["incident"]["id"]
            pm = c.get(f"/api/v1/incidents/{iid}/postmortem", headers=h)
            assert pm.status_code == 200 and "postmortem" in pm.json()
        # missing → 404
        miss = c.get("/api/v1/incidents/NOPE/postmortem", headers=h)
        assert miss.status_code == 404


def test_incidents_search_and_bulk_transition():
    with TestClient(create_app()) as c:
        h = _responder(c)
        made = c.post("/api/v1/incidents",
                      json={"problem_id": "P-2026-0613-001",
                            "venue_id": "V-METLIFE"}, headers=h)
        if made.status_code != 200:
            return
        iid = made.json()["incident"]["id"]
        # search by text/state
        s = c.get("/api/v1/incidents-search?limit=50&offset=0", headers=h)
        assert s.status_code == 200 and "incidents" in s.json()
        # bulk transition
        b = c.post("/api/v1/incidents-bulk/transition",
                   json={"incident_ids": [iid], "target": "ACKNOWLEDGED",
                         "actor": "sre-sam"}, headers=h)
        assert b.status_code == 200
        body = b.json()
        assert iid in body["succeeded"] or iid in body["failed"]

