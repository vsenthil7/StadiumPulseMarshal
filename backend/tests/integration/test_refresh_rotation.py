"""OIDC/session refresh-token rotation, theft detection and revocation."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.refresh_store import RefreshStore, ReuseError

PW = "MatchdayDemo123!"


def _client() -> TestClient:
    return TestClient(create_app())


def _login(c: TestClient) -> dict:
    r = c.post("/api/v1/auth/login",
               json={"email": "operator@arena-north.demo", "password": PW})
    assert r.status_code == 200
    return r.json()


# ── store unit behaviour ────────────────────────────────────────────────────
def test_store_rotation_issues_new_token_same_family():
    s = RefreshStore()
    t1, fam = s.issue("alice")
    rotated = s.rotate(t1)
    assert rotated is not None
    t2, fam2 = rotated
    assert t2 != t1
    assert fam2 == fam  # same family
    assert s.subject_for(t2) == "alice"
    # the old token is now consumed
    assert s.subject_for(t1) is None


def test_store_reuse_revokes_family():
    s = RefreshStore()
    t1, fam = s.issue("bob")
    t2, _ = s.rotate(t1)
    # replaying t1 (already rotated) is theft → ReuseError + family revoked
    try:
        s.rotate(t1)
        assert False, "expected ReuseError"
    except ReuseError:
        pass
    assert s.is_family_revoked(fam)
    # and the previously-valid t2 is now dead too
    assert s.rotate(t2) is None
    assert s.subject_for(t2) is None


def test_store_revoke_token():
    s = RefreshStore()
    t1, fam = s.issue("carol")
    s.revoke_token(t1)
    assert s.is_family_revoked(fam)
    assert s.rotate(t1) is None


# ── endpoint behaviour ──────────────────────────────────────────────────────
def test_login_returns_refresh_token():
    with _client() as c:
        body = _login(c)
        assert body.get("refresh_token")


def test_refresh_rotation_endpoint():
    with _client() as c:
        body = _login(c)
        rt = body["refresh_token"]
        r = c.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert r.status_code == 200
        out = r.json()
        assert out["token"]
        assert out["refresh_token"] and out["refresh_token"] != rt
        # rotating the OLD token again → reuse → 401
        bad = c.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert bad.status_code == 401
        # and the rotated-to token is now also dead (family revoked)
        dead = c.post("/api/v1/auth/refresh",
                      json={"refresh_token": out["refresh_token"]})
        assert dead.status_code == 401


def test_logout_revokes_refresh_family():
    with _client() as c:
        body = _login(c)
        rt = body["refresh_token"]
        assert c.post("/api/v1/auth/logout",
                      json={"refresh_token": rt}).status_code == 200
        # after logout the refresh token can't be rotated
        assert c.post("/api/v1/auth/refresh",
                      json={"refresh_token": rt}).status_code == 401


def test_invalid_refresh_token_rejected():
    with _client() as c:
        assert c.post("/api/v1/auth/refresh",
                      json={"refresh_token": "nonsense"}).status_code == 401
