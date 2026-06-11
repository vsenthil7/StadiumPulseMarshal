"""Integration tests exercising the full API surface."""
from __future__ import annotations

from app.core.config import Settings
from app.core.context import AppContext
from app.main import create_app
from fastapi.testclient import TestClient


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_config(client):
    body = client.get("/api/v1/config").json()
    assert body["data_source"] == "mock"
    assert body["agent_backend"] == "mock"


def test_problems_list_and_open_only(client):
    allp = client.get("/api/v1/problems").json()["problems"]
    openp = client.get("/api/v1/problems?open_only=true").json()["problems"]
    assert len(allp) == 3
    assert len(openp) == 2


def test_get_problem_and_404(client):
    ok = client.get("/api/v1/problems/P-2026-0613-001")
    assert ok.status_code == 200
    assert ok.json()["root_cause"]["children"][0]["entity_name"] == "payments-postgres"
    assert client.get("/api/v1/problems/MISSING").status_code == 404


def test_entities_and_timeline(client):
    assert len(client.get("/api/v1/entities").json()["entities"]) == 5
    assert len(client.get("/api/v1/timeline").json()["timeline"]) == 7


def test_analyze_and_404(client):
    body = client.post("/api/v1/agent/analyze/P-2026-0613-001").json()
    assert body["analysis"]["confidence"] == 0.91
    assert len(body["analysis"]["recommended_actions"]) == 2
    assert client.post("/api/v1/agent/analyze/MISSING").status_code == 404


def test_remediation_lifecycle(client):
    analysis = client.post("/api/v1/agent/analyze/P-2026-0613-001").json()
    aid = analysis["analysis"]["recommended_actions"][0]["id"]

    # listing
    assert len(client.get("/api/v1/remediations").json()["actions"]) >= 1
    assert isinstance(
        client.get("/api/v1/remediations?pending=true").json()["actions"], list
    )

    # cannot execute before approval
    assert client.post(f"/api/v1/remediations/{aid}/execute").status_code == 409

    # approve -> execute
    appr = client.post(
        f"/api/v1/remediations/{aid}/approve",
        json={"decided_by": "jane", "reason": "surge confirmed"},
    ).json()
    assert appr["action"]["status"] == "APPROVED"
    ex = client.post(f"/api/v1/remediations/{aid}/execute").json()
    assert ex["executed"] is True
    assert ex["action"]["status"] == "EXECUTED"

    # audit reflects decision
    assert len(client.get("/api/v1/audit").json()["decisions"]) >= 1


def test_reject_flow(client):
    analysis = client.post("/api/v1/agent/analyze/P-2026-0613-001").json()
    aid = analysis["analysis"]["recommended_actions"][1]["id"]
    rej = client.post(
        f"/api/v1/remediations/{aid}/reject",
        json={"decided_by": "jane", "reason": "too risky mid-match"},
    ).json()
    assert rej["action"]["status"] == "REJECTED"


def test_decision_on_missing_remediation(client):
    assert (
        client.post(
            "/api/v1/remediations/NOPE/approve", json={"decided_by": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/remediations/NOPE/reject", json={"decided_by": "x"}
        ).status_code
        == 404
    )
    assert client.post("/api/v1/remediations/NOPE/execute").status_code == 404


def test_settings_update(client):
    body = client.patch(
        "/api/v1/settings",
        json={"auto_approve_low_risk": True, "max_auto_approve_severity": "HIGH"},
    ).json()
    assert body["auto_approve_low_risk"] is True


def test_auto_approve_guardrail_applies_on_analyze():
    # Build an app whose settings auto-approve low-risk within ceiling.
    settings = Settings(
        use_mocks=True, auto_approve_low_risk=True, max_auto_approve_severity="HIGH"
    )
    app = create_app()
    with TestClient(app) as c:
        # Replace context with auto-approve-enabled one.
        app.state.ctx = AppContext(settings)
        body = c.post("/api/v1/agent/analyze/P-2026-0613-001").json()
        statuses = [a["status"] for a in body["analysis"]["recommended_actions"]]
        # The LOW-risk action should be auto-approved.
        assert "AUTO_APPROVED" in statuses


def test_websocket_stream(client):
    with client.websocket_connect("/api/v1/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "problem_feed"
        assert msg["count"] == 2
        assert len(msg["problems"]) == 2
