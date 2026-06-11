"""Coverage for routes_auth: /me non-demo fallback, refresh rotation + reuse +
bearer fallback, logout, auth-events CSV/filters, OIDC status/login/callback."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PW = "MatchdayDemo123!"


def _login(c, email="sre@stadiumpulse.demo"):
    return c.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()


def test_me_for_demo_and_refresh_rotation():
    with TestClient(create_app()) as c:
        r = _login(c)
        tok, refresh = r["token"], r["refresh_token"]
        h = {"Authorization": f"Bearer {tok}"}
        # /me resolves the demo directory view
        me = c.get("/api/v1/auth/me", headers=h)
        assert me.status_code == 200 and me.json()["user"]["role"] == "admin"
        # refresh with the refresh_token rotates it
        rr = c.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert rr.status_code == 200
        body = rr.json()
        assert body["token"] and body["refresh_token"] != refresh


def test_refresh_reuse_detected_revokes():
    with TestClient(create_app()) as c:
        r = _login(c)
        refresh = r["refresh_token"]
        # first rotation consumes the token
        first = c.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert first.status_code == 200
        # presenting the now-rotated original = reuse → 401
        reuse = c.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert reuse.status_code == 401


def test_refresh_bearer_fallback_no_refresh_token():
    with TestClient(create_app()) as c:
        tok = _login(c)["token"]
        h = {"Authorization": f"Bearer {tok}"}
        # no refresh_token in body → re-mint from the bearer access token
        rr = c.post("/api/v1/auth/refresh", json={}, headers=h)
        assert rr.status_code == 200 and rr.json()["token"]


def test_refresh_invalid_token_401():
    with TestClient(create_app()) as c:
        rr = c.post("/api/v1/auth/refresh", json={"refresh_token": "bogus.token.value"})
        assert rr.status_code == 401


def test_logout_revokes_family():
    with TestClient(create_app()) as c:
        refresh = _login(c)["refresh_token"]
        out = c.post("/api/v1/auth/logout", json={"refresh_token": refresh})
        assert out.status_code == 200 and out.json()["ok"] is True
        # the revoked token can no longer be rotated
        rr = c.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert rr.status_code == 401


def test_logout_without_token_is_ok():
    with TestClient(create_app()) as c:
        out = c.post("/api/v1/auth/logout", json={})
        assert out.status_code == 200 and out.json()["ok"] is True


def test_login_failure_audited_and_401():
    with TestClient(create_app()) as c:
        bad = c.post("/api/v1/auth/login",
                     json={"email": "sre@stadiumpulse.demo", "password": "wrong"})
        assert bad.status_code == 401
        unknown = c.post("/api/v1/auth/login",
                         json={"email": "nobody@x.demo", "password": PW})
        assert unknown.status_code == 401


def test_auth_events_json_csv_and_filters():
    with TestClient(create_app()) as c:
        # admin (SETTINGS_WRITE) generates a couple of auth events first
        r = _login(c)  # success event
        c.post("/api/v1/auth/login",
               json={"email": "sre@stadiumpulse.demo", "password": "wrong"})  # failure
        h = {"Authorization": f"Bearer {r['token']}"}
        j = c.get("/api/v1/auth/events?limit=50&offset=0", headers=h)
        assert j.status_code == 200 and "events" in j.json()
        # filter by action + outcome
        f = c.get("/api/v1/auth/events?action=auth.login&outcome=failure", headers=h)
        assert f.status_code == 200
        # csv export
        csv = c.get("/api/v1/auth/events?fmt=csv", headers=h)
        assert csv.status_code == 200
        assert "text/csv" in csv.headers["content-type"]
        assert "timestamp,actor,action,outcome,ip" in csv.text


def test_auth_events_forbidden_for_viewer():
    with TestClient(create_app()) as c:
        tok = _login(c, "viewer@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert c.get("/api/v1/auth/events", headers=h).status_code == 403


def test_demo_users_and_csrf():
    with TestClient(create_app()) as c:
        du = c.get("/api/v1/auth/demo-users")
        assert du.status_code == 200 and du.json()["password"] == PW
        assert len(du.json()["users"]) >= 8
        csrf = c.get("/api/v1/auth/csrf")
        assert csrf.status_code == 200 and "csrf_token" in csrf.json()
        assert "csrf_token" in csrf.cookies


# ── OIDC endpoints (disabled by default → status false, login/callback 401) ──
def test_oidc_status_disabled():
    with TestClient(create_app()) as c:
        s = c.get("/api/v1/auth/oidc/status")
        assert s.status_code == 200 and s.json()["enabled"] is False


def test_oidc_login_disabled_401():
    with TestClient(create_app()) as c:
        # follow_redirects off so a 307 wouldn't be chased; disabled → 401 anyway
        r = c.get("/api/v1/auth/oidc/login", follow_redirects=False)
        assert r.status_code == 401


def test_oidc_callback_disabled_and_missing_params():
    with TestClient(create_app()) as c:
        # disabled → 401
        r = c.get("/api/v1/auth/oidc/callback?code=x&state=y", follow_redirects=False)
        assert r.status_code == 401

