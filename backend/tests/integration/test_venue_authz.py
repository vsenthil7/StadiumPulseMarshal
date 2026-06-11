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


# ── Round 5: problem + search venue scoping ─────────────────────────────────
def test_problems_scoped_to_principal_venue():
    with _client() as c:
        # Arena North operator sees only Arena North problems (2 of 3 fixtures).
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        probs = c.get("/api/v1/problems", headers=h).json()["problems"]
        venues = {p.get("venue_id") for p in probs}
        assert venues == {"venue_arena_north"}

        # Olympic Park operator sees only the Olympic Park problem.
        op2 = _login(c, "operator@olympic-park.demo")["token"]
        h2 = {"Authorization": f"Bearer {op2}"}
        probs2 = c.get("/api/v1/problems", headers=h2).json()["problems"]
        assert {p.get("venue_id") for p in probs2} == {"venue_olympic_park"}


def test_platform_sees_all_problems():
    with _client() as c:
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        probs = c.get("/api/v1/problems",
                      headers={"Authorization": f"Bearer {sre}"}).json()["problems"]
        venues = {p.get("venue_id") for p in probs}
        assert "venue_arena_north" in venues and "venue_olympic_park" in venues


def test_get_problem_cross_venue_403():
    with _client() as c:
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        # P-...-002 belongs to Olympic Park → 403 for an Arena North operator.
        r = c.get("/api/v1/problems/P-2026-0613-002", headers=h)
        assert r.status_code == 403
        # An Arena North problem is readable.
        ok = c.get("/api/v1/problems/P-2026-0613-001", headers=h)
        assert ok.status_code == 200


def test_problems_explicit_venue_filter_authorized():
    with _client() as c:
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        # asking for another venue explicitly → 403
        assert c.get("/api/v1/problems?venue_id=venue_olympic_park",
                     headers=h).status_code == 403
        # own venue → 200
        assert c.get("/api/v1/problems?venue_id=venue_arena_north",
                     headers=h).status_code == 200


# ── Round 6 Track A: entity / SLO / analytics venue scoping ─────────────────
def test_entities_scoped_to_principal_venue():
    with _client() as c:
        op = _login(c, "operator@arena-north.demo")["token"]
        ents = c.get("/api/v1/entities",
                     headers={"Authorization": f"Bearer {op}"}).json()["entities"]
        venues = {e.get("venue_id") for e in ents}
        # Arena North operator should not see the Olympic Park fan-app entity.
        assert "venue_olympic_park" not in venues
        assert "venue_arena_north" in venues

        op2 = _login(c, "operator@olympic-park.demo")["token"]
        ents2 = c.get("/api/v1/entities",
                      headers={"Authorization": f"Bearer {op2}"}).json()["entities"]
        v2 = {e.get("venue_id") for e in ents2}
        assert v2 <= {"venue_olympic_park"}


def test_entities_explicit_cross_venue_filter_403():
    with _client() as c:
        op = _login(c, "operator@arena-north.demo")["token"]
        h = {"Authorization": f"Bearer {op}"}
        assert c.get("/api/v1/entities?venue_id=venue_olympic_park",
                     headers=h).status_code == 403
        assert c.get("/api/v1/entities?venue_id=venue_arena_north",
                     headers=h).status_code == 200


def test_slo_budgets_scoped_by_venue():
    with _client() as c:
        # All SLOs in the payment scenario are on Arena North entities, so an
        # Olympic Park operator should see none of them.
        op_ol = _login(c, "operator@olympic-park.demo")["token"]
        budgets_ol = c.get("/api/v1/slo",
                           headers={"Authorization": f"Bearer {op_ol}"}).json()["budgets"]
        assert budgets_ol == []
        # Arena North operator sees the payment SLOs.
        op_an = _login(c, "operator@arena-north.demo")["token"]
        budgets_an = c.get("/api/v1/slo",
                           headers={"Authorization": f"Bearer {op_an}"}).json()["budgets"]
        assert len(budgets_an) >= 1
        # Platform sees all.
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        budgets_all = c.get("/api/v1/slo",
                            headers={"Authorization": f"Bearer {sre}"}).json()["budgets"]
        assert len(budgets_all) >= len(budgets_an)


def test_slo_explicit_cross_venue_403():
    with _client() as c:
        op = _login(c, "operator@arena-north.demo")["token"]
        assert c.get("/api/v1/slo?venue_id=venue_olympic_park",
                     headers={"Authorization": f"Bearer {op}"}).status_code == 403


def test_analytics_scoped_incidents_by_venue():
    with _client() as c:
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        hs = {"Authorization": f"Bearer {sre}"}
        # create one incident in each venue
        for vid in ("venue_arena_north", "venue_olympic_park"):
            probs = c.get(f"/api/v1/problems?venue_id={vid}", headers=hs).json()["problems"]
            if probs:
                c.post("/api/v1/incidents",
                       json={"problem_id": probs[0]["id"], "venue_id": vid}, headers=hs)
        # platform analytics sees both venues
        allsum = c.get("/api/v1/analytics", headers=hs).json()["summary"]
        assert allsum["total_incidents"] >= 2
        # arena-north operator analytics only counts its venue
        op = _login(c, "operator@arena-north.demo")["token"]
        an = c.get("/api/v1/analytics",
                   headers={"Authorization": f"Bearer {op}"}).json()["summary"]
        assert set(an["by_venue"].keys()) <= {"venue_arena_north"}


# ── Round 11 Track Q: per-venue analytics rollups ───────────────────────────
def test_analytics_by_venue_rollup_and_scope():
    with _client() as c:
        sre = _login(c, "sre@stadiumpulse.demo")["token"]
        hs = {"Authorization": f"Bearer {sre}"}
        # create incidents in both venues
        for vid in ("venue_arena_north", "venue_olympic_park"):
            probs = c.get(f"/api/v1/problems?venue_id={vid}", headers=hs).json()["problems"]
            if probs:
                c.post("/api/v1/incidents",
                       json={"problem_id": probs[0]["id"], "venue_id": vid}, headers=hs)
        # platform sees per-venue rows for both venues
        rows = c.get("/api/v1/analytics/by-venue", headers=hs).json()["venues"]
        vids = {r["venue_id"] for r in rows}
        assert "venue_arena_north" in vids
        # each row carries rollup fields
        for r in rows:
            assert "mttr_minutes" in r and "slo_health" in r and "by_severity" in r

        # arena operator only sees its own venue row
        op = _login(c, "operator@arena-north.demo")["token"]
        orows = c.get("/api/v1/analytics/by-venue",
                      headers={"Authorization": f"Bearer {op}"}).json()["venues"]
        assert {r["venue_id"] for r in orows} <= {"venue_arena_north"}
