"""Davis AI feedback loop (M8)."""
from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _h(c, email="responder@arena-north.demo"):
    tok = c.post("/api/v1/auth/login",
                 json={"email": email, "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_problem_analysis_returns_structure():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/davis/problems/P-1/analysis", headers=_h(c))
        assert r.status_code == 200
        assert r.json()["problem_id"] == "P-1"


def test_feedback_updates_rank():
    with TestClient(create_app()) as c:
        h = _h(c)
        r1 = c.post("/api/v1/davis/feedback",
                    json={"problem_id": "P-9", "correct": True}, headers=h).json()
        assert r1["rank"] == 1.0
        r2 = c.post("/api/v1/davis/feedback",
                    json={"problem_id": "P-9", "correct": True}, headers=h).json()
        assert r2["rank"] == 2.0
        r3 = c.post("/api/v1/davis/feedback",
                    json={"problem_id": "P-9", "correct": False}, headers=h).json()
        assert r3["rank"] == 1.0


def test_feedback_list_and_ranked():
    with TestClient(create_app()) as c:
        h = _h(c)
        c.post("/api/v1/davis/feedback",
               json={"problem_id": "P-A", "correct": True}, headers=h)
        fb = c.get("/api/v1/davis/problems/P-A/feedback", headers=h).json()
        assert fb["rank"] == 1.0 and len(fb["feedback"]) == 1
        ranked = c.get("/api/v1/davis/ranked", headers=h).json()["problems"]
        assert any(p["problem_id"] == "P-A" for p in ranked)


def test_feedback_requires_approve_permission():
    with TestClient(create_app()) as c:
        # viewer lacks REMEDIATION_APPROVE
        r = c.post("/api/v1/davis/feedback",
                   json={"problem_id": "P-Z", "correct": True},
                   headers=_h(c, "viewer@arena-north.demo"))
        assert r.status_code == 403
