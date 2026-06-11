"""SLO catalog (M4): list/get + burn policy."""
from __future__ import annotations
from fastapi.testclient import TestClient
from app.main import create_app

PW = "MatchdayDemo123!"


def _h(c, email="viewer@arena-north.demo"):
    tok = c.post("/api/v1/auth/login",
                 json={"email": email, "password": PW}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_list_slo_catalog_nonempty():
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/slo-catalog", headers=_h(c))
        assert r.status_code == 200 and len(r.json()) >= 1


def test_get_slo_definition():
    with TestClient(create_app()) as c:
        h = _h(c)
        first = c.get("/api/v1/slo-catalog", headers=h).json()[0]
        r = c.get(f"/api/v1/slo-catalog/{first['id']}", headers=h)
        assert r.status_code == 200 and r.json()["id"] == first["id"]


def test_get_missing_slo_404():
    with TestClient(create_app()) as c:
        assert c.get("/api/v1/slo-catalog/nope", headers=_h(c)).status_code == 404


def test_burn_policy_lists_tiers():
    with TestClient(create_app()) as c:
        h = _h(c)
        sid = c.get("/api/v1/slo-catalog", headers=h).json()[0]["id"]
        bp = c.get(f"/api/v1/slo-catalog/{sid}/burn-policy", headers=h).json()
        names = {t["name"] for t in bp["burn_tiers"]}
        assert {"fast", "medium", "slow", "trickle"} <= names
        assert bp["allowed_error_fraction"] >= 0


def test_burn_policy_trigger_scales_with_factor():
    with TestClient(create_app()) as c:
        h = _h(c)
        sid = c.get("/api/v1/slo-catalog", headers=h).json()[0]["id"]
        tiers = {t["name"]: t for t in
                 c.get(f"/api/v1/slo-catalog/{sid}/burn-policy", headers=h).json()["burn_tiers"]}
        assert tiers["fast"]["trigger_error_rate"] >= tiers["trickle"]["trigger_error_rate"]


def test_filter_by_service_id():
    with TestClient(create_app()) as c:
        h = _h(c)
        all_slos = c.get("/api/v1/slo-catalog", headers=h).json()
        svc = all_slos[0]["service_id"]
        filt = c.get(f"/api/v1/slo-catalog?service_id={svc}", headers=h).json()
        assert all(s["service_id"] == svc for s in filt)
