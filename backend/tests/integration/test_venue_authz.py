"""Venue-scoped authorization, /auth/me rehydration and /venues directory."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.rbac.policy import Principal, Role

PW = "MatchdayDemo123!"


def _client() -> TestClient:
    return TestClient(create_app())


def _login(c: TestClient, email: str) -> dict:
    r = c.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()


# ── Principal.can_access_venue unit behaviour ───────────────────────────────
def test_principal_venue_scope():
    scoped = Principal(subject="a", roles=[Role.OPERATOR], venues=["v1"])
    assert scoped.can_access_venue("v1")
    assert not scoped.can_access_venue("v2")
    assert scoped.can_access_venue(None)  # unscoped resource allowed

    platform = Principal(subject="b", roles=[Role.ADMIN], all_venues=True)
    assert platform.can_access_venue("v1")
    assert platform.can_access_venue("anything")


# ── /auth/me ────────────────────────────────────────────────────────────────
def test_auth_me_rehydrates():
    with _client() as c:
        tok = _login(c, "responder@arena-north.demo")["token"]
        r = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        user = r.json()["user"]
        assert user["role"] == "responder"
        assert user["venue_id"] == "venue_arena_north"
        assert user["all_venues"] is False


def test_auth_me_requires_token():
    with _client() as c:
        # No token + auth disabled → anonymous admin (still resolves, cross-venue).
        r = c.get("/api/v1/auth/me")
        assert r.status_code == 200
        assert r.json()["user"]["all_venues"] is True


# ── /venues directory is principal-scoped ───────────────────────────────────
def test_venues_scoped_to_principal():
    with _client() as c:
        # venue-scoped operator sees only their venue
        op = _login(c, "operator@arena-north.demo")["token"]
        r = c.get("/api/v1/venues", headers={"Authorization": f"Bearer {op}"})
        assert r.status_code == 200
        body = r.json()
        ids = {v["id"] for v in body["venues"]}
        assert ids == {"venue_arena_north"}
        assert body["all_venues"] is False

        # platform admin sees the whole estate
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        r2 = c.get("/api/v1/venues", headers={"Authorization": f"Bearer {sre}"})
        ids2 = {v["id"] for v in r2.json()["venues"]}
        assert ids2 == {"venue_arena_north", "venue_olympic_park"}
        assert r2.json()["all_venues"] is True


# ── cross-venue enforcement on incidents ────────────────────────────────────
def test_incident_list_cross_venue_forbidden():
    with _client() as c:
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        # own venue: ok
        assert c.get("/api/v1/incidents?venue_id=venue_arena_north", headers=h).status_code == 200
        # other venue: 403
        assert c.get("/api/v1/incidents?venue_id=venue_olympic_park", headers=h).status_code == 403


def test_incident_create_cross_venue_forbidden():
    with _client() as c:
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        problems = c.get("/api/v1/problems?open_only=true", headers=h).json()["problems"]
        pid = problems[0]["id"]
        # creating in another venue is forbidden
        r = c.post("/api/v1/incidents",
                   json={"problem_id": pid, "venue_id": "venue_olympic_park"},
                   headers=h)
        assert r.status_code == 403
        # creating in own venue is allowed
        ok = c.post("/api/v1/incidents",
                    json={"problem_id": pid, "venue_id": "venue_arena_north"},
                    headers=h)
        assert ok.status_code == 201


def test_platform_admin_any_venue():
    with _client() as c:
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        h = {"Authorization": f"Bearer {sre}"}
        assert c.get("/api/v1/incidents?venue_id=venue_olympic_park", headers=h).status_code == 200
        assert c.get("/api/v1/incidents?venue_id=venue_arena_north", headers=h).status_code == 200


def _create_incident_in(c: TestClient, token: str, venue_id: str) -> str:
    h = {"Authorization": f"Bearer {token}"}
    problems = c.get("/api/v1/problems?open_only=true", headers=h).json()["problems"]
    pid = problems[0]["id"]
    r = c.post("/api/v1/incidents",
               json={"problem_id": pid, "venue_id": venue_id}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["incident"]["id"]


def test_per_entity_venue_enforcement():
    """An operator may not act on another venue's incident by id."""
    with _client() as c:
        sre = _login(c, "sre@stadiumpulse.demo")["token"]  # cross-venue
        # incident lives in Olympic Park
        iid = _create_incident_in(c, sre, "venue_olympic_park")

        # Arena North operator must be 403 on every sub-route for it.
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        assert c.get(f"/api/v1/incidents/{iid}", headers=h).status_code == 403
        assert c.post(f"/api/v1/incidents/{iid}/transition",
                      json={"target": "ACKNOWLEDGED", "actor": "op"},
                      headers=h).status_code == 403
        assert c.post(f"/api/v1/incidents/{iid}/assign",
                      json={"assignee": "x", "actor": "op"},
                      headers=h).status_code == 403
        assert c.post(f"/api/v1/incidents/{iid}/note",
                      json={"note": "x", "actor": "op"},
                      headers=h).status_code == 403
        assert c.post(f"/api/v1/incidents/{iid}/escalate",
                      headers=h).status_code == 403


def test_per_entity_same_venue_allowed():
    with _client() as c:
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        iid = _create_incident_in(c, sre, "venue_arena_north")
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        # same venue: read + act allowed
        assert c.get(f"/api/v1/incidents/{iid}", headers=h).status_code == 200
        assert c.post(f"/api/v1/incidents/{iid}/note",
                      json={"note": "looking", "actor": "op"},
                      headers=h).status_code == 200


def test_platform_admin_acts_any_venue_entity():
    with _client() as c:
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        h = {"Authorization": f"Bearer {sre}"}
        iid = _create_incident_in(c, sre, "venue_olympic_park")
        assert c.get(f"/api/v1/incidents/{iid}", headers=h).status_code == 200
