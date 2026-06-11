"""ChatOps (M6): Slack slash command."""
from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import create_app


def _cmd(c, text):
    return c.post("/api/v1/chatops/slack/command",
                  data={"command": "/marshal", "text": text,
                        "user_name": "sre1"})


def test_status_command():
    with TestClient(create_app()) as c:
        r = _cmd(c, "status")
        assert r.status_code == 200
        assert "Status" in r.json()["text"]


def test_help_default():
    with TestClient(create_app()) as c:
        r = _cmd(c, "")
        assert r.status_code == 200 and "Commands" in r.json()["text"]


def test_runbook_show():
    with TestClient(create_app()) as c:
        r = _cmd(c, "runbook RB-db-pool-scale")
        body = r.json()
        assert "Runbook:" in body["text"] and "Connection Pool" in body["text"]


def test_runbook_execute():
    with TestClient(create_app()) as c:
        r = _cmd(c, "runbook RB-db-pool-scale execute")
        assert "Execution" in r.json()["text"]


def test_runbook_not_found():
    with TestClient(create_app()) as c:
        r = _cmd(c, "runbook NOPE")
        assert "not found" in r.json()["text"]


def test_incident_not_found():
    with TestClient(create_app()) as c:
        r = _cmd(c, "incident INC-doesnotexist")
        assert "not found" in r.json()["text"]
