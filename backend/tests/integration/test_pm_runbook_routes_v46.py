"""Cover routes_postmortems and routes_runbooks: full CRUD lifecycles + 404s."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PW = "MatchdayDemo123!"


def _h(c):
    tok = c.post("/api/v1/auth/login",
                 json={"email": "sre@stadiumpulse.demo", "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


# ── postmortems ──
def test_postmortem_full_crud_and_404s():
    with TestClient(create_app()) as c:
        h = _h(c)
        # create
        cr = c.post("/api/v1/postmortems",
                    json={"title": "DB outage", "incident_id": "INC-1",
                          "severity": "SEV1", "summary": "pool exhausted"}, headers=h)
        assert cr.status_code == 200
        pid = cr.json()["id"]
        # list (+ filters)
        assert c.get("/api/v1/postmortems", headers=h).status_code == 200
        assert c.get("/api/v1/postmortems?status=draft", headers=h).status_code == 200
        assert c.get("/api/v1/postmortems?incident_id=INC-1", headers=h).status_code == 200
        # get
        assert c.get(f"/api/v1/postmortems/{pid}", headers=h).status_code == 200
        assert c.get("/api/v1/postmortems/NOPE", headers=h).status_code == 404
        # patch
        up = c.patch(f"/api/v1/postmortems/{pid}",
                     json={"root_cause": "connection storm"}, headers=h)
        assert up.status_code == 200 and up.json()["root_cause"] == "connection storm"
        assert c.patch("/api/v1/postmortems/NOPE", json={"x": 1}, headers=h).status_code == 404
        # timeline
        tl = c.post(f"/api/v1/postmortems/{pid}/timeline",
                    json={"text": "alert fired"}, headers=h)
        assert tl.status_code == 200 and len(tl.json()["timeline"]) == 1
        assert c.post("/api/v1/postmortems/NOPE/timeline",
                      json={"text": "x"}, headers=h).status_code == 404
        # action + complete
        ac = c.post(f"/api/v1/postmortems/{pid}/actions",
                    json={"description": "add alarm", "owner": "sam"}, headers=h)
        assert ac.status_code == 200
        aid = ac.json()["action_items"][0]["id"]
        assert c.post("/api/v1/postmortems/NOPE/actions",
                      json={"description": "x"}, headers=h).status_code == 404
        comp = c.post(f"/api/v1/postmortems/{pid}/actions/{aid}/complete", headers=h)
        assert comp.status_code == 200 and comp.json()["action_items"][0]["done"] is True
        assert c.post("/api/v1/postmortems/NOPE/actions/x/complete",
                      headers=h).status_code == 404
        # publish
        pub = c.post(f"/api/v1/postmortems/{pid}/publish", headers=h)
        assert pub.status_code == 200 and pub.json()["status"] == "published"
        assert c.post("/api/v1/postmortems/NOPE/publish", headers=h).status_code == 404
        # export markdown
        ex = c.get(f"/api/v1/postmortems/{pid}/export", headers=h)
        assert ex.status_code == 200 and ex.text.startswith("# Postmortem: DB outage")
        assert c.get("/api/v1/postmortems/NOPE/export", headers=h).status_code == 404


# ── runbooks ──
def test_runbook_full_crud_execute_and_404s():
    with TestClient(create_app()) as c:
        h = _h(c)
        # list seeded + filters
        lst = c.get("/api/v1/runbooks", headers=h)
        assert lst.status_code == 200 and len(lst.json()["runbooks"]) >= 2
        assert c.get("/api/v1/runbooks?category=database", headers=h).status_code == 200
        assert c.get("/api/v1/runbooks?tag=matchday", headers=h).status_code == 200
        # get seeded + 404
        assert c.get("/api/v1/runbooks/RB-db-pool-scale", headers=h).status_code == 200
        assert c.get("/api/v1/runbooks/NOPE", headers=h).status_code == 404
        # create
        cr = c.post("/api/v1/runbooks",
                    json={"name": "Cache flush", "category": "incident",
                          "description": "flush hot cache", "tags": ["cache"],
                          "steps": []}, headers=h)
        assert cr.status_code == 200
        rid = cr.json()["id"]
        # patch + 404
        up = c.patch(f"/api/v1/runbooks/{rid}",
                     json={"description": "flush v2"}, headers=h)
        assert up.status_code == 200 and up.json()["description"] == "flush v2"
        assert c.patch("/api/v1/runbooks/NOPE", json={"x": 1}, headers=h).status_code == 404
        # execute + 404
        ex = c.post(f"/api/v1/runbooks/{rid}/execute", json={}, headers=h)
        assert ex.status_code == 200 and ex.json()["status"] == "completed"
        assert c.post("/api/v1/runbooks/NOPE/execute", json={}, headers=h).status_code == 404
        # executions list
        exs = c.get("/api/v1/runbook-executions", headers=h)
        assert exs.status_code == 200 and "executions" in exs.json()
        assert c.get(f"/api/v1/runbook-executions?runbook_id={rid}", headers=h).status_code == 200
        # delete + 404
        d = c.delete(f"/api/v1/runbooks/{rid}", headers=h)
        assert d.status_code == 200 and d.json()["deleted"] is True
        assert c.delete("/api/v1/runbooks/NOPE", headers=h).status_code == 404


# ── enterprise: cost-analytics, change-events, fleet ──
def test_enterprise_endpoints():
    with TestClient(create_app()) as c:
        h = _h(c)
        # cost analytics
        ca = c.get("/api/v1/cost-analytics", headers=h)
        assert ca.status_code == 200 and "services" in ca.json()
        assert c.get("/api/v1/cost-analytics?venue_id=venue_arena_north",
                     headers=h).status_code == 200
        # record a change event
        cr = c.post("/api/v1/change-events",
                    json={"title": "deploy api v2", "service_id": "svc-api",
                          "change_type": "deployment"}, headers=h)
        assert cr.status_code == 200
        eid = cr.json()["id"]
        # list + filters
        assert c.get("/api/v1/change-events", headers=h).status_code == 200
        assert c.get("/api/v1/change-events?service_id=svc-api",
                     headers=h).status_code == 200
        # link to an incident + 404 on missing event
        lk = c.post(f"/api/v1/change-events/{eid}/link/INC-1", headers=h)
        assert lk.status_code == 200 and "INC-1" in lk.json()["linked_incident_ids"]
        assert c.post("/api/v1/change-events/NOPE/link/INC-1",
                      headers=h).status_code == 404
        # correlate: valid ISO + bad timestamp 400
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        ok = c.get(f"/api/v1/change-events/correlate?incident_time={now_iso}", headers=h)
        assert ok.status_code == 200 and "events" in ok.json()
        bad = c.get("/api/v1/change-events/correlate?incident_time=not-a-date", headers=h)
        assert bad.status_code == 400
        # fleet rollup
        fl = c.get("/api/v1/fleet", headers=h)
        assert fl.status_code == 200 and "venues" in fl.json()

