"""Integration tests for Phase 3 middleware, observability and routes."""
from __future__ import annotations


import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.context import AppContext
from app.main import create_app
from app.observability.metrics import reset_metrics


@pytest.fixture
def client():
    get_settings.cache_clear()
    reset_metrics()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _incident(client) -> str:
    return client.post(
        "/api/v1/incidents", json={"problem_id": "P-2026-0613-001"}
    ).json()["incident"]["id"]


# --- middleware ---
def test_correlation_id_header(client):
    r = client.get("/api/v1/health")
    assert "X-Request-ID" in r.headers
    # inbound id is echoed
    r2 = client.get("/api/v1/health", headers={"X-Request-ID": "my-trace-1"})
    assert r2.headers["X-Request-ID"] == "my-trace-1"


def test_error_envelope_on_404(client):
    r = client.get("/api/v1/incidents/NOPE")
    body = r.json()
    assert r.status_code == 404
    assert set(body["error"].keys()) == {"code", "message", "request_id", "details"}
    assert body["error"]["code"] == "not_found"


def test_validation_error_envelope(client):
    # invalid transition target triggers request validation (422)
    iid = _incident(client)
    r = client.post(f"/api/v1/incidents/{iid}/transition", json={"target": "BOGUS"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


# --- observability ---
def test_metrics_endpoint(client):
    client.get("/api/v1/health")
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    assert "stadiumpulse_requests_total" in r.text
    assert "# TYPE" in r.text


def test_ready_endpoint(client):
    r = client.get("/api/v1/ready").json()
    assert r["status"] == "ready"
    assert "persistence" in r["checks"]


def test_metrics_increment_on_incident(client):
    _incident(client)
    text = client.get("/api/v1/metrics").text
    assert "stadiumpulse_incidents_created_total" in text


# --- webhooks ---
def test_webhook_crud(client):
    created = client.post(
        "/api/v1/webhooks",
        json={"url": "http://hook.test/x", "event_types": ["incident.created"]},
    )
    assert created.status_code == 201
    wid = created.json()["webhook"]["id"]
    lst = client.get("/api/v1/webhooks").json()
    assert len(lst["webhooks"]) == 1
    assert client.delete(f"/api/v1/webhooks/{wid}").status_code == 204
    assert client.delete(f"/api/v1/webhooks/{wid}").status_code == 404


# --- analysis routes ---
def test_postmortem_route(client):
    iid = _incident(client)
    client.post(f"/api/v1/incidents/{iid}/transition", json={"target": "ACKNOWLEDGED"})
    client.post(f"/api/v1/incidents/{iid}/transition", json={"target": "RESOLVED"})
    pm = client.get(f"/api/v1/incidents/{iid}/postmortem").json()["postmortem"]
    assert pm["incident_id"] == iid
    assert pm["markdown"].startswith("# Postmortem")
    assert client.get("/api/v1/incidents/NOPE/postmortem").status_code == 404


def test_slo_trends_route(client):
    client.get("/api/v1/slo")
    trends = client.get("/api/v1/slo/trends").json()["trends"]
    assert len(trends) >= 1
    assert "direction" in trends[0]


def test_incident_search_route(client):
    _incident(client)
    r = client.get("/api/v1/incidents-search?severity=HIGH").json()
    assert r["page"]["total"] == 1
    r2 = client.get("/api/v1/incidents-search?text=payment").json()
    assert r2["page"]["total"] == 1


def test_bulk_transition_route(client):
    iid = _incident(client)
    r = client.post(
        "/api/v1/incidents-bulk/transition",
        json={"incident_ids": [iid, "MISSING"], "target": "ACKNOWLEDGED"},
    ).json()
    assert iid in r["succeeded"]
    assert "MISSING" in r["failed"]


# --- RBAC ---
import contextlib


@contextlib.contextmanager
def _app_with_settings(**kw):
    """Yield a TestClient whose app boots (via lifespan) with given settings."""
    import app.core.config as cfg
    import app.main as main_mod

    original_cfg = cfg.get_settings
    original_main = main_mod.get_settings
    settings = Settings(use_mocks=True, **kw)
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    main_mod.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        cfg.get_settings = original_cfg
        main_mod.get_settings = original_main


def _rbac_client(**kw):
    with _app_with_settings(auth_enabled=True, **kw) as c:
        yield c


def test_rbac_viewer_cannot_write():
    gen = _rbac_client(jwt_secret="js")
    c = next(gen)
    viewer = jwt.encode({"sub": "v", "roles": ["viewer"]}, "js", algorithm="HS256")
    h = {"Authorization": f"Bearer {viewer}"}
    # viewer can read
    assert c.get("/api/v1/incidents", headers=h).status_code == 200
    # viewer cannot create
    r = c.post("/api/v1/incidents", json={"problem_id": "P-2026-0613-001"}, headers=h)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_rbac_operator_can_write_incidents_not_webhooks():
    gen = _rbac_client(jwt_secret="js")
    c = next(gen)
    op = jwt.encode({"sub": "o", "roles": ["operator"]}, "js", algorithm="HS256")
    h = {"Authorization": f"Bearer {op}"}
    assert c.post("/api/v1/incidents", json={"problem_id": "P-2026-0613-001"},
                  headers=h).status_code == 201
    # webhooks require admin
    assert c.get("/api/v1/webhooks", headers=h).status_code == 403


def test_rbac_admin_full_access():
    gen = _rbac_client(jwt_secret="js")
    c = next(gen)
    admin = jwt.encode({"sub": "a", "roles": ["admin"]}, "js", algorithm="HS256")
    h = {"Authorization": f"Bearer {admin}"}
    assert c.get("/api/v1/webhooks", headers=h).status_code == 200


def test_rbac_api_key_default_admin():
    gen = _rbac_client(api_key="k")
    c = next(gen)
    assert c.get("/api/v1/webhooks", headers={"X-API-Key": "k"}).status_code == 200


# --- rate limiting ---
def test_rate_limiting():
    with _app_with_settings(rate_limit_enabled=True, rate_limit_per_minute=3) as c:
        codes = [c.get("/api/v1/scenarios").status_code for _ in range(6)]
        assert 429 in codes
        # metrics endpoint is exempt
        assert c.get("/api/v1/metrics").status_code == 200
