"""Demo auth login + remediation RBAC enforcement.

Locks in the authorization fix: the remediation approve/reject/execute routes
now require ``remediation:approve``. A viewer JWT is forbidden; a responder JWT
passes the gate; with auth disabled and no token the demo runs as admin.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

PW = "MatchdayDemo123!"


def _client() -> TestClient:
    return TestClient(create_app())


def _login(c: TestClient, email: str) -> str:
    r = c.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_login_success_and_failure():
    with _client() as c:
        r = c.post("/api/v1/auth/login",
                   json={"email": "responder@arena-north.demo", "password": PW})
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["role"] == "responder"
        assert body["user"]["venue_id"] == "venue_arena_north"
        assert body["token"]
        # wrong password
        bad = c.post("/api/v1/auth/login",
                     json={"email": "responder@arena-north.demo", "password": "nope"})
        assert bad.status_code == 401
        # unknown user
        nouser = c.post("/api/v1/auth/login",
                        json={"email": "ghost@nowhere.demo", "password": PW})
        assert nouser.status_code == 401


def test_demo_users_listing():
    with _client() as c:
        r = c.get("/api/v1/auth/demo-users")
        assert r.status_code == 200
        data = r.json()
        assert data["password"] == PW
        emails = {u["email"] for u in data["users"]}
        assert "viewer@arena-north.demo" in emails
        assert "admin@olympic-park.demo" in emails


def _pending_action_id(c: TestClient, token: str) -> str:
    probs = c.get("/api/v1/problems?open_only=true",
                  headers={"Authorization": f"Bearer {token}"}).json()["problems"]
    assert probs, "expected seeded problems"
    pid = probs[0]["id"]
    c.post(f"/api/v1/agent/analyze/{pid}",
           headers={"Authorization": f"Bearer {token}"})
    actions = c.get("/api/v1/remediations?pending=true",
                    headers={"Authorization": f"Bearer {token}"}).json()["actions"]
    assert actions, "expected a pending remediation after analyze"
    return actions[0]["id"]


def test_viewer_forbidden_responder_allowed_on_approve():
    with _client() as c:
        responder = _login(c, "responder@arena-north.demo")
        viewer = _login(c, "viewer@arena-north.demo")
        action_id = _pending_action_id(c, responder)

        # viewer lacks remediation:approve → 403
        forbidden = c.post(
            f"/api/v1/remediations/{action_id}/approve",
            json={"decided_by": "viewer", "reason": "x"},
            headers={"Authorization": f"Bearer {viewer}"},
        )
        assert forbidden.status_code == 403

        # responder has it → 200
        ok = c.post(
            f"/api/v1/remediations/{action_id}/approve",
            json={"decided_by": "responder", "reason": "ok"},
            headers={"Authorization": f"Bearer {responder}"},
        )
        assert ok.status_code == 200


def test_no_token_is_anonymous_admin_when_auth_disabled():
    with _client() as c:
        admin = _login(c, "admin@arena-north.demo")
        action_id = _pending_action_id(c, admin)
        # No Authorization header → ANONYMOUS_ADMIN (demo runs unguarded).
        r = c.post(
            f"/api/v1/remediations/{action_id}/approve",
            json={"decided_by": "anon", "reason": "x"},
        )
        assert r.status_code == 200


def test_viewer_cannot_change_settings():
    with _client() as c:
        viewer = _login(c, "viewer@arena-north.demo")
        r = c.patch("/api/v1/settings", json={"auto_approve_low_risk": True},
                    headers={"Authorization": f"Bearer {viewer}"})
        assert r.status_code == 403
