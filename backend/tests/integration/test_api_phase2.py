"""Integration tests for the expanded API (incidents, ops, auth)."""
from __future__ import annotations

import asyncio

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.context import AppContext
from app.main import create_app


@pytest.fixture
def client():
    from app.core.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _create_incident(client) -> str:
    body = client.post(
        "/api/v1/incidents",
        json={"problem_id": "P-2026-0613-001", "venue_id": "V-METLIFE"},
    ).json()
    return body["incident"]["id"]


def test_incident_create_list_get(client):
    iid = _create_incident(client)
    assert iid.startswith("INC-")
    lst = client.get("/api/v1/incidents?limit=10&offset=0").json()
    assert lst["page"]["total"] == 1
    assert len(lst["incidents"]) == 1
    one = client.get(f"/api/v1/incidents/{iid}").json()
    assert one["incident"]["id"] == iid
    assert client.get("/api/v1/incidents/MISSING").status_code == 404


def test_incident_create_missing_problem(client):
    r = client.post("/api/v1/incidents", json={"problem_id": "NOPE"})
    assert r.status_code == 404


def test_incident_lifecycle_transitions(client):
    iid = _create_incident(client)
    ack = client.post(f"/api/v1/incidents/{iid}/transition",
                      json={"target": "ACKNOWLEDGED", "actor": "jane"})
    assert ack.status_code == 200
    assert ack.json()["incident"]["state"] == "ACKNOWLEDGED"
    # illegal transition -> 409
    bad = client.post(f"/api/v1/incidents/{iid}/transition",
                      json={"target": "CLOSED"})
    assert bad.status_code == 409
    # missing incident -> 404
    miss = client.post("/api/v1/incidents/MISSING/transition",
                       json={"target": "ACKNOWLEDGED"})
    assert miss.status_code == 404


def test_incident_assign_note_escalate(client):
    iid = _create_incident(client)
    a = client.post(f"/api/v1/incidents/{iid}/assign",
                    json={"assignee": "sre-sam"})
    assert a.json()["incident"]["assignee"] == "sre-sam"
    n = client.post(f"/api/v1/incidents/{iid}/note", json={"note": "looking"})
    assert any(e["type"] == "NOTE" for e in n.json()["incident"]["timeline"])
    e = client.post(f"/api/v1/incidents/{iid}/escalate")
    assert e.status_code == 200
    # error paths
    assert client.post("/api/v1/incidents/X/assign",
                       json={"assignee": "y"}).status_code == 404
    assert client.post("/api/v1/incidents/X/note",
                       json={"note": "y"}).status_code == 404
    assert client.post("/api/v1/incidents/X/escalate").status_code == 404


def test_slo_analytics_notifications(client):
    slo = client.get("/api/v1/slo").json()
    assert len(slo["budgets"]) == 2
    an = client.get("/api/v1/analytics").json()
    assert "total_incidents" in an["summary"]
    nt = client.get("/api/v1/notifications").json()
    assert "notifications" in nt
    # filtered by incident
    iid = _create_incident(client)
    ntf = client.get(f"/api/v1/notifications?incident_id={iid}").json()
    assert isinstance(ntf["notifications"], list)


def test_scenarios_list_and_select(client):
    sc = client.get("/api/v1/scenarios").json()
    assert len(sc["scenarios"]) == 4
    assert sc["active"] == "payment_db_saturation"
    sw = client.post("/api/v1/scenarios/select",
                     json={"key": "cdn_edge_failure"}).json()
    assert sw["active"] == "cdn_edge_failure"
    probs = client.get("/api/v1/problems?open_only=true").json()
    assert probs["problems"][0]["id"] == "P-AZTECA-001"


def test_analytics_after_resolution(client):
    iid = _create_incident(client)
    client.post(f"/api/v1/incidents/{iid}/transition",
                json={"target": "ACKNOWLEDGED"})
    client.post(f"/api/v1/incidents/{iid}/transition",
                json={"target": "RESOLVED"})
    an = client.get("/api/v1/analytics").json()["summary"]
    assert an["resolved_incidents"] == 1
    assert an["mttr_minutes"] is not None


# --- auth ---
def _auth_app(**kw):
    app = create_app()
    settings = Settings(use_mocks=True, auth_enabled=True, **kw)
    with TestClient(app) as c:
        ctx = AppContext(settings)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(ctx.startup())
        finally:
            loop.close()
        app.state.ctx = ctx
        yield c


def test_auth_api_key():
    gen = _auth_app(api_key="secret", jwt_secret="js")
    c = next(gen)
    assert c.get("/api/v1/incidents").status_code == 401
    assert c.get("/api/v1/incidents",
                 headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/api/v1/incidents",
                 headers={"X-API-Key": "secret"}).status_code == 200


def test_auth_jwt():
    gen = _auth_app(api_key="secret", jwt_secret="js")
    c = next(gen)
    tok = jwt.encode({"sub": "alice", "roles": ["admin"]}, "js", algorithm="HS256")
    assert c.get("/api/v1/incidents",
                 headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    bad = jwt.encode({"sub": "x", "roles": ["admin"]}, "wrong", algorithm="HS256")
    assert c.get("/api/v1/incidents",
                 headers={"Authorization": f"Bearer {bad}"}).status_code == 401
    # bearer with no jwt_secret configured -> 401
    gen2 = _auth_app(api_key="secret")
    c2 = next(gen2)
    assert c2.get("/api/v1/incidents",
                  headers={"Authorization": f"Bearer {tok}"}).status_code == 401


# --- context helpers ---
async def test_context_scenario_switch_and_slo():
    ctx = AppContext(Settings(use_mocks=True))
    await ctx.startup()
    ctx.set_scenario("network_partition")
    assert ctx.current_scenario == "network_partition"
    budgets = await ctx.evaluate_slos()
    assert isinstance(budgets, list)
    summary = await ctx.analytics()
    assert summary.total_incidents == 0
    await ctx.shutdown()
