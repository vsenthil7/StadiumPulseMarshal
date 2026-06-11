"""Integration tests for Phase 4 API surface + SQL repo coverage."""
from __future__ import annotations

import contextlib

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.observability.metrics import reset_metrics


@pytest.fixture
def client():
    get_settings.cache_clear()
    reset_metrics()
    with TestClient(create_app()) as c:
        yield c


@contextlib.contextmanager
def _app_with_settings(**kw):
    import app.core.config as cfg
    import app.main as main_mod

    original_cfg, original_main = cfg.get_settings, main_mod.get_settings
    settings = Settings(use_mocks=True, **kw)
    cfg.get_settings = lambda: settings  # type: ignore
    main_mod.get_settings = lambda: settings  # type: ignore
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        cfg.get_settings = original_cfg
        main_mod.get_settings = original_main


def _incident(client, **headers) -> str:
    return client.post(
        "/api/v1/incidents", json={"problem_id": "P-2026-0613-001"},
        headers=headers,
    ).json()["incident"]["id"]


# --- idempotency ---
def test_idempotent_create(client):
    h = {"Idempotency-Key": "key-1"}
    a = _incident(client, **h)
    b = _incident(client, **h)
    assert a == b
    assert client.get("/api/v1/incidents").json()["page"]["total"] == 1
    # different key -> new incident
    _incident(client, **{"Idempotency-Key": "key-2"})
    assert client.get("/api/v1/incidents").json()["page"]["total"] == 2


# --- optimistic concurrency ---
def test_optimistic_concurrency(client):
    iid = _incident(client)
    # stale version rejected
    r = client.post(f"/api/v1/incidents/{iid}/transition",
                    json={"target": "ACKNOWLEDGED", "expected_version": 5})
    assert r.status_code == 409
    # correct version accepted, version bumps
    ok = client.post(f"/api/v1/incidents/{iid}/transition",
                     json={"target": "ACKNOWLEDGED", "expected_version": 0})
    assert ok.status_code == 200
    assert ok.json()["incident"]["version"] == 1


# --- trace context ---
def test_trace_context_new_and_continued(client):
    r = client.get("/api/v1/health")
    assert "traceparent" in r.headers
    # continue an inbound trace
    tid = "0af7651916cd43dd8448eb211c80319c"
    r2 = client.get(
        "/api/v1/health",
        headers={"traceparent": f"00-{tid}-b7ad6b7169203331-01"},
    )
    assert tid in r2.headers["traceparent"]


def test_error_envelope_has_trace_id(client):
    r = client.get("/api/v1/incidents/NOPE")
    assert r.status_code == 404
    assert "trace_id" in r.json()["error"]


# --- audit query ---
def test_audit_query_endpoint(client):
    iid = _incident(client)
    client.post(f"/api/v1/incidents/{iid}/transition",
                json={"target": "ACKNOWLEDGED"})
    res = client.get("/api/v1/audit-log").json()
    assert len(res["entries"]) >= 2
    # filter by action
    res2 = client.get("/api/v1/audit-log?action=incident.create").json()
    assert all(e["action"] == "incident.create" for e in res2["entries"])
    # cursor paging
    res3 = client.get("/api/v1/audit-log?limit=1").json()
    assert res3["page"]["limit"] == 1
    if res3["page"]["has_more"]:
        cursor = res3["page"]["next_cursor"]
        res4 = client.get(f"/api/v1/audit-log?limit=1&cursor={cursor}").json()
        assert res4["entries"][0]["id"] != res3["entries"][0]["id"]


# --- readiness probe ---
def test_ready_probes_dependencies(client):
    r = client.get("/api/v1/ready").json()
    assert r["status"] == "ready"
    assert r["checks"]["persistence"].startswith("ok")
    assert r["checks"]["observability_client"].startswith("ok")


# --- dead-letter + redrive ---
def test_webhook_dead_letter_and_redrive(client):
    # register a webhook to a black-hole URL, then drive an event so it fails.
    created = client.post(
        "/api/v1/webhooks",
        json={"url": "http://127.0.0.1:9/none", "event_types": ["incident.created"]},
    ).json()["webhook"]
    wid = created["id"]
    # trigger delivery via the outbox relay path by creating an incident, then
    # draining; in mock the relay loop is running, so just create + poll.
    _incident(client)
    # dead-letter list endpoint reachable
    dl = client.get("/api/v1/webhooks/dead-letter/list")
    assert dl.status_code == 200
    # redrive a (possibly not-yet-dead) webhook resets its state
    rr = client.post(f"/api/v1/webhooks/{wid}/redrive")
    assert rr.status_code == 200
    assert rr.json()["webhook"]["dead_lettered"] is False
    # redrive missing -> 404
    assert client.post("/api/v1/webhooks/NOPE/redrive").status_code == 404


# --- config self-check at startup ---
def test_startup_fails_on_bad_config():
    from app.core.config import ConfigurationError

    with pytest.raises(ConfigurationError):
        with _app_with_settings(auth_enabled=True):  # no key/secret
            pass


# --- SQL repos: outbox + audit log durability ---
def test_sql_outbox_and_audit(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/p4.db"
    with _app_with_settings(database_url=db_url) as c:
        iid = _incident(c)
        c.post(f"/api/v1/incidents/{iid}/transition",
               json={"target": "ACKNOWLEDGED"})
        # audit persisted to SQL
        res = c.get("/api/v1/audit-log").json()
        assert len(res["entries"]) >= 2
    # reopen the same DB: audit entries survive
    with _app_with_settings(database_url=db_url) as c2:
        res2 = c2.get("/api/v1/audit-log").json()
        assert len(res2["entries"]) >= 2
