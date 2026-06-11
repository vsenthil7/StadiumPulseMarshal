"""Postmortem workflow: create/update/timeline/actions/publish/export + RBAC."""
from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _h(c, email="operator@arena-north.demo"):
    tok = c.post("/api/v1/auth/login",
                 json={"email": email, "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _mk(c, h):
    return c.post("/api/v1/postmortems",
                  json={"title": "Payments outage", "severity": "page",
                        "summary": "DB pool exhausted"}, headers=h).json()


def test_create_and_get():
    with TestClient(create_app()) as c:
        h = _h(c)
        pm = _mk(c, h)
        assert pm["id"].startswith("PM-") and pm["status"] == "draft"
        assert c.get(f"/api/v1/postmortems/{pm['id']}", headers=h).status_code == 200


def test_list_and_filter():
    with TestClient(create_app()) as c:
        h = _h(c)
        _mk(c, h)
        lst = c.get("/api/v1/postmortems?status=draft", headers=h).json()["postmortems"]
        assert all(p["status"] == "draft" for p in lst) and len(lst) >= 1


def test_timeline_and_actions():
    with TestClient(create_app()) as c:
        h = _h(c)
        pid = _mk(c, h)["id"]
        c.post(f"/api/v1/postmortems/{pid}/timeline",
               json={"text": "alert fired"}, headers=h)
        pm = c.post(f"/api/v1/postmortems/{pid}/actions",
                    json={"description": "add pool autoscaling", "owner": "sre"},
                    headers=h).json()
        assert len(pm["timeline"]) == 1 and len(pm["action_items"]) == 1
        aid = pm["action_items"][0]["id"]
        done = c.post(f"/api/v1/postmortems/{pid}/actions/{aid}/complete",
                      headers=h).json()
        assert done["action_items"][0]["done"] is True


def test_publish_and_export():
    with TestClient(create_app()) as c:
        h = _h(c)
        pid = _mk(c, h)["id"]
        c.post(f"/api/v1/postmortems/{pid}/timeline",
               json={"text": "mitigated"}, headers=h)
        pub = c.post(f"/api/v1/postmortems/{pid}/publish", headers=h).json()
        assert pub["status"] == "published"
        md = c.get(f"/api/v1/postmortems/{pid}/export", headers=h)
        assert md.status_code == 200 and "# Postmortem: Payments outage" in md.text
        assert "## Timeline" in md.text


def test_update_fields():
    with TestClient(create_app()) as c:
        h = _h(c)
        pid = _mk(c, h)["id"]
        upd = c.patch(f"/api/v1/postmortems/{pid}",
                      json={"root_cause": "pool ceiling too low"}, headers=h).json()
        assert upd["root_cause"] == "pool ceiling too low"


def test_write_requires_permission():
    with TestClient(create_app()) as c:
        # viewer has POSTMORTEM_READ but not WRITE
        r = c.post("/api/v1/postmortems", json={"title": "x"},
                   headers=_h(c, "viewer@arena-north.demo"))
        assert r.status_code == 403
