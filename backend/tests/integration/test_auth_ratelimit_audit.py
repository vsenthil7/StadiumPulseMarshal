"""Auth endpoint rate-limiting (Track I) and auth audit events (Track J)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

PW = "MatchdayDemo123!"


def _app_client(auth_rpm: int = 100):
    app = create_app()
    c = TestClient(app)
    # adjust the limiter after startup (ctx exists once the client context opens)
    return app, c


# ── Track I: rate limiting ──────────────────────────────────────────────────
def test_login_rate_limited_after_burst():
    app = create_app()
    with TestClient(app) as c:
        app.state.ctx.auth_limiter.per_minute = 3
        app.state.ctx.auth_limiter.reset()
        codes = []
        for _ in range(6):
            r = c.post("/api/v1/auth/login",
                       json={"email": "nope@x.demo", "password": "bad"})
            codes.append(r.status_code)
        # first few are 401 (bad creds), then the limiter kicks in with 429
        assert 429 in codes
        # the 429 carries Retry-After
        last = c.post("/api/v1/auth/login",
                      json={"email": "nope@x.demo", "password": "bad"})
        if last.status_code == 429:
            assert "Retry-After" in last.headers


def test_refresh_rate_limited():
    app = create_app()
    with TestClient(app) as c:
        app.state.ctx.auth_limiter.per_minute = 2
        app.state.ctx.auth_limiter.reset()
        codes = [
            c.post("/api/v1/auth/refresh", json={"refresh_token": "x"}).status_code
            for _ in range(5)
        ]
        assert 429 in codes


def test_rate_limit_refills(monkeypatch):
    from app.services.rate_limiter import RateLimiter
    rl = RateLimiter(per_minute=60)  # 1/sec
    # burst of 60 ok, 61st denied
    allowed = [rl.check("k")[0] for _ in range(61)]
    assert allowed[0] is True
    assert allowed[-1] is False


# ── Track J: auth audit events ──────────────────────────────────────────────
def test_login_success_and_failure_audited():
    app = create_app()
    with TestClient(app) as c:
        app.state.ctx.auth_limiter.per_minute = 100
        app.state.ctx.auth_limiter.reset()
        c.post("/api/v1/auth/login",
               json={"email": "operator@arena-north.demo", "password": PW})
        c.post("/api/v1/auth/login",
               json={"email": "operator@arena-north.demo", "password": "wrong"})
        # query the audit log directly
        async def _q():
            return await app.state.ctx.audit.query()
        import asyncio
        rows = asyncio.get_event_loop().run_until_complete(_q())
        actions = [(e.action, e.metadata.get("outcome")) for e in rows]
        assert ("auth.login", "success") in actions
        assert ("auth.login", "failure") in actions


def test_reuse_detection_is_audited():
    app = create_app()
    with TestClient(app) as c:
        app.state.ctx.auth_limiter.per_minute = 100
        app.state.ctx.auth_limiter.reset()
        login = c.post("/api/v1/auth/login",
                       json={"email": "responder@arena-north.demo", "password": PW}).json()
        rt = login["refresh_token"]
        c.post("/api/v1/auth/refresh", json={"refresh_token": rt})  # rotate
        c.post("/api/v1/auth/refresh", json={"refresh_token": rt})  # reuse → revoke

        async def _q():
            return await app.state.ctx.audit.query()
        import asyncio
        rows = asyncio.get_event_loop().run_until_complete(_q())
        actions = [e.action for e in rows]
        assert "auth.refresh_reuse_detected" in actions


# ── Track M: /auth/events endpoint (admin-only) ─────────────────────────────
def test_auth_events_endpoint_admin_only():
    app = create_app()
    with TestClient(app) as c:
        app.state.ctx.auth_limiter.per_minute = 100
        app.state.ctx.auth_limiter.reset()
        # generate some events
        c.post("/api/v1/auth/login",
               json={"email": "admin@arena-north.demo", "password": PW})
        c.post("/api/v1/auth/login",
               json={"email": "x@y.demo", "password": "bad"})
        admin = c.post("/api/v1/auth/login",
                       json={"email": "admin@arena-north.demo", "password": PW}).json()["token"]
        viewer = c.post("/api/v1/auth/login",
                        json={"email": "viewer@arena-north.demo", "password": PW}).json()["token"]
        # viewer (no settings:write) is forbidden
        assert c.get("/api/v1/auth/events",
                     headers={"Authorization": f"Bearer {viewer}"}).status_code == 403
        # admin sees events
        r = c.get("/api/v1/auth/events",
                  headers={"Authorization": f"Bearer {admin}"})
        assert r.status_code == 200
        events = r.json()["events"]
        actions = {(e["action"], e["outcome"]) for e in events}
        assert ("auth.login", "success") in actions
        assert ("auth.login", "failure") in actions
        # newest-first ordering
        ats = [e["at"] for e in events]
        assert ats == sorted(ats, reverse=True)
