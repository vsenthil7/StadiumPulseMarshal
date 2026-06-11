"""Runbook library: CRUD + execute + RBAC."""
from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _tok(c, email):
    return c.post("/api/v1/auth/login",
                  json={"email": email, "password": PW}).json()["token"]


def _h(c, email="responder@arena-north.demo"):
    return {"Authorization": f"Bearer {_tok(c, email)}"}


def test_list_seeded_runbooks():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/runbooks", headers=_h(c, "viewer@arena-north.demo"))
        assert r.status_code == 200
        names = [x["name"] for x in r.json()["runbooks"]]
        assert any("Connection Pool" in n for n in names)


def test_get_runbook():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/runbooks/RB-db-pool-scale", headers=_h(c))
        assert r.status_code == 200 and r.json()["category"] == "database"


def test_get_missing_runbook_404():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/runbooks/nope", headers=_h(c))
        assert r.status_code == 404


def test_filter_by_category_and_tag():
    with TestClient(create_app()) as c:
        h = _h(c)
        byc = c.get("/api/v1/runbooks?category=scaling", headers=h).json()["runbooks"]
        assert all(r["category"] == "scaling" for r in byc)
        byt = c.get("/api/v1/runbooks?tag=matchday", headers=h).json()["runbooks"]
        assert all("matchday" in r["tags"] for r in byt)


def test_create_runbook():
    with TestClient(create_app()) as c:
        body = {"name": "Cache Flush", "category": "custom",
                "tags": ["cache"], "steps": [
                    {"order": 1, "title": "Flush", "description": "redis FLUSHALL"}]}
        r = c.post("/api/v1/runbooks", json=body, headers=_h(c))
        assert r.status_code == 200
        rid = r.json()["id"]
        assert rid.startswith("RB-")
        # readable back
        assert c.get(f"/api/v1/runbooks/{rid}", headers=_h(c)).status_code == 200


def test_update_bumps_version():
    with TestClient(create_app()) as c:
        h = _h(c)
        v0 = c.get("/api/v1/runbooks/RB-svc-scaleout", headers=h).json()["version"]
        upd = c.patch("/api/v1/runbooks/RB-svc-scaleout",
                      json={"description": "updated"}, headers=h).json()
        assert upd["version"] == v0 + 1 and upd["description"] == "updated"


def test_execute_runbook_records_execution():
    with TestClient(create_app()) as c:
        h = _h(c)
        r = c.post("/api/v1/runbooks/RB-db-pool-scale/execute",
                   json={"incident_id": "INC-1"}, headers=h)
        assert r.status_code == 200
        ex = r.json()
        assert ex["status"] == "completed" and ex["runbook_id"] == "RB-db-pool-scale"
        # execution listed
        lst = c.get("/api/v1/runbook-executions?runbook_id=RB-db-pool-scale",
                    headers=h).json()["executions"]
        assert len(lst) >= 1


def test_create_requires_write_permission():
    with TestClient(create_app()) as c:
        r = c.post("/api/v1/runbooks", json={"name": "x"},
                   headers=_h(c, "viewer@arena-north.demo"))
        assert r.status_code == 403


def test_delete_runbook():
    with TestClient(create_app()) as c:
        h = _h(c)
        rid = c.post("/api/v1/runbooks", json={"name": "Temp"}, headers=h).json()["id"]
        assert c.delete(f"/api/v1/runbooks/{rid}", headers=h).status_code == 200
        assert c.get(f"/api/v1/runbooks/{rid}", headers=h).status_code == 404
