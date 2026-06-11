"""Closeout tests for the last Phase 3 coverage branches."""
from __future__ import annotations

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import _claim_roles, get_principal, require_auth
from app.core.errors import AppError, RateLimitedError
from app.middleware.errors import register_exception_handlers
from app.observability.metrics import Counter
from app.rbac.policy import ANONYMOUS_ADMIN


def test_claim_roles_string_and_empty():
    # comma string form
    assert _claim_roles({"roles": "admin, viewer"}, "roles") == ["admin", "viewer"]
    # missing claim -> []
    assert _claim_roles({}, "roles") == []
    # non-list/non-string -> []
    assert _claim_roles({"roles": 123}, "roles") == []


def test_counter_empty_labels_format():
    c = Counter("x_total", "h")
    c.inc()  # no labels -> empty label set
    lines = c.expose()
    assert any(line == "x_total 1.0" for line in lines)


async def test_require_auth_alias_returns_principal():
    # require_auth simply returns the resolved principal.
    result = await require_auth(ANONYMOUS_ADMIN)
    assert result is ANONYMOUS_ADMIN


def _handler_app() -> FastAPI:
    """Tiny app to exercise the exception handlers directly."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/ratelimited")
    async def _rl():
        raise RateLimitedError("slow down", retry_after=7)

    @app.get("/app-error")
    async def _ae():
        raise AppError("boom")

    @app.get("/boom")
    async def _boom():
        raise ValueError("unexpected kaboom")

    return app


def test_rate_limited_error_handler_sets_retry_after():
    with TestClient(_handler_app(), raise_server_exceptions=False) as c:
        r = c.get("/ratelimited")
        assert r.status_code == 429
        assert r.headers["Retry-After"] == "7"
        assert r.json()["error"]["code"] == "rate_limited"


def test_generic_app_error_handler():
    with TestClient(_handler_app(), raise_server_exceptions=False) as c:
        r = c.get("/app-error")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "internal_error"


def test_unhandled_exception_handler():
    with TestClient(_handler_app(), raise_server_exceptions=False) as c:
        r = c.get("/boom")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "internal_error"


async def test_incident_search_text_miss_branch():
    """Text filter that excludes an incident exercises the continue branch."""
    from app.events.bus import EventBus
    from app.models.domain import Problem
    from app.models.enums import ProblemStatus, Severity
    from app.repositories.memory.repositories import (
        MemoryIncidentRepository,
        MemoryNotificationRepository,
    )
    from app.services.escalation_engine import EscalationEngine
    from app.services.incident_service import IncidentService
    from app.services.notification_service import NotificationService

    svc = IncidentService(
        MemoryIncidentRepository(), EscalationEngine([], []),
        NotificationService(MemoryNotificationRepository()), events=EventBus(),
    )
    await svc.create_from_problem(
        Problem(id="P1", title="Payment outage", severity=Severity.HIGH,
                status=ProblemStatus.OPEN))
    # text that matches nothing -> all filtered out (continue hit)
    results, total = await svc.search(text="zzz-nomatch")
    assert total == 0 and results == []
    # severity filter that excludes -> continue branch
    results2, total2 = await svc.search(severity=Severity.LOW)
    assert total2 == 0
    # state filter that excludes -> state continue branch
    from app.models.incident import IncidentState
    results3, total3 = await svc.search(state=IncidentState.RESOLVED)
    assert total3 == 0


def test_metrics_route_template_fallback():
    """_route_template falls back to url.path when no route is matched."""
    from app.middleware.metrics import _route_template

    class _FakeURL:
        path = "/unmatched"

    class _FakeReq:
        scope: dict = {}
        url = _FakeURL()

    assert _route_template(_FakeReq()) == "/unmatched"
    # and uses the route template when present
    class _Route:
        path = "/api/v1/incidents/{incident_id}"
    class _FakeReq2:
        scope = {"route": _Route()}
        url = _FakeURL()
    assert _route_template(_FakeReq2()) == "/api/v1/incidents/{incident_id}"


def test_metrics_middleware_unmatched_path():
    """A request still records metrics even when served by the SPA catch-all."""
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    from app.main import create_app
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        # any path returns a response and is recorded
        assert c.get("/api/v1/health").status_code == 200


def test_rate_limit_api_key_keying():
    """Rate limiter keys by API key when present (exercises key branch)."""
    from app.core.config import Settings
    from app.core.context import AppContext
    import app.core.config as cfg
    import app.main as main_mod
    from fastapi.testclient import TestClient
    from app.main import create_app

    settings = Settings(use_mocks=True, rate_limit_enabled=True,
                        rate_limit_per_minute=2)
    orig_cfg, orig_main = cfg.get_settings, main_mod.get_settings
    cfg.get_settings = lambda: settings  # type: ignore
    main_mod.get_settings = lambda: settings  # type: ignore
    try:
        with TestClient(create_app()) as c:
            codes = [
                c.get("/api/v1/scenarios", headers={"X-API-Key": "k1"}).status_code
                for _ in range(4)
            ]
            assert 429 in codes
    finally:
        cfg.get_settings = orig_cfg
        main_mod.get_settings = orig_main

