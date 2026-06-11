"""Unit tests for Phase 3 cross-cutting modules."""
from __future__ import annotations

import pytest

from app.core.errors import (
    AppError,
    ConflictError,
    NotFoundError,
    RateLimitedError,
    error_envelope,
)
from app.events.bus import DomainEvent, EventBus, EventType
from app.middleware.correlation import get_request_id, set_request_id
from app.models.webhook import WebhookSubscription
from app.observability.metrics import (
    Counter,
    Histogram,
    MetricsRegistry,
    get_metrics,
    reset_metrics,
)
from app.rbac.policy import (
    ANONYMOUS_ADMIN,
    Permission,
    Principal,
    Role,
    roles_from_names,
)


# --- errors ---
def test_error_envelope_shape():
    env = error_envelope("not_found", "missing", "rid-1", {"x": 1})
    assert env["error"]["code"] == "not_found"
    assert env["error"]["request_id"] == "rid-1"
    assert env["error"]["details"] == {"x": 1}


def test_app_error_subclasses():
    assert NotFoundError("x").status_code == 404
    assert ConflictError("x").status_code == 409
    rl = RateLimitedError("slow down", retry_after=5)
    assert rl.status_code == 429
    assert rl.retry_after == 5
    base = AppError("boom", details={"a": 1})
    assert base.details == {"a": 1}


# --- correlation ---
def test_correlation_context():
    set_request_id("abc")
    assert get_request_id() == "abc"


# --- metrics ---
def test_counter():
    c = Counter("c_total", "help")
    assert c.value() == 0.0
    c.inc(method="GET")
    c.inc(2.0, method="GET")
    assert c.value(method="GET") == 3.0
    lines = c.expose()
    assert any("c_total" in line for line in lines)


def test_counter_empty_expose():
    c = Counter("empty_total", "h")
    lines = c.expose()
    assert "empty_total 0" in lines


def test_histogram():
    h = Histogram("h_seconds", "help", buckets=(0.1, 0.5, 1.0))
    h.observe(0.05, method="GET")
    h.observe(0.3, method="GET")
    h.observe(5.0, method="GET")  # overflow bucket
    lines = h.expose()
    assert any("h_seconds_bucket" in line for line in lines)
    assert any("h_seconds_sum" in line for line in lines)
    assert any('le="+Inf"' in line for line in lines)


def test_metrics_registry_render():
    reg = MetricsRegistry()
    reg.observe_request("GET", "/x", 200, 0.01)
    reg.incidents_created.inc(severity="HIGH")
    text = reg.render()
    assert "stadiumpulse_requests_total" in text
    assert "stadiumpulse_incidents_created_total" in text
    assert "stadiumpulse_request_duration_seconds" in text


def test_metrics_singleton_and_reset():
    reset_metrics()
    a = get_metrics()
    b = get_metrics()
    assert a is b
    reset_metrics()
    assert get_metrics() is not a


# --- RBAC ---
def test_principal_permissions():
    viewer = Principal(subject="v", roles=[Role.VIEWER])
    assert viewer.has(Permission.INCIDENT_READ)
    assert not viewer.has(Permission.INCIDENT_WRITE)
    admin = Principal(subject="a", roles=[Role.ADMIN])
    assert admin.has(Permission.WEBHOOK_ADMIN)
    responder = Principal(subject="r", roles=[Role.RESPONDER])
    assert responder.has(Permission.REMEDIATION_APPROVE)


def test_roles_from_names_filters_unknown():
    roles = roles_from_names(["admin", "bogus", "viewer"])
    assert Role.ADMIN in roles
    assert Role.VIEWER in roles
    assert len(roles) == 2


def test_anonymous_admin_is_full_access():
    assert ANONYMOUS_ADMIN.has(Permission.SETTINGS_WRITE)


# --- event bus ---
async def test_event_bus_typed_and_wildcard():
    bus = EventBus()
    seen: list[str] = []

    async def typed(ev: DomainEvent) -> None:
        seen.append(f"typed:{ev.type.value}")

    async def wild(ev: DomainEvent) -> None:
        seen.append(f"wild:{ev.type.value}")

    bus.subscribe(EventType.INCIDENT_CREATED, typed)
    bus.subscribe(None, wild)
    n = await bus.publish(
        DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="I1")
    )
    assert n == 2
    assert "typed:incident.created" in seen
    assert "wild:incident.created" in seen


async def test_event_bus_no_handlers():
    bus = EventBus()
    assert await bus.publish(DomainEvent(type=EventType.SLO_BREACHED)) == 0


async def test_event_bus_handler_failure_isolated():
    bus = EventBus()
    ok: list[int] = []

    async def boom(_ev: DomainEvent) -> None:
        raise RuntimeError("nope")

    async def good(_ev: DomainEvent) -> None:
        ok.append(1)

    bus.subscribe(EventType.INCIDENT_CREATED, boom)
    bus.subscribe(EventType.INCIDENT_CREATED, good)
    await bus.publish(DomainEvent(type=EventType.INCIDENT_CREATED))
    assert ok == [1]


# --- webhook model ---
def test_webhook_wants():
    wh = WebhookSubscription(url="http://x", event_types=[EventType.INCIDENT_CREATED])
    assert wh.wants(EventType.INCIDENT_CREATED)
    assert not wh.wants(EventType.SLO_BREACHED)
    allw = WebhookSubscription(url="http://x", event_types=[])
    assert allw.wants(EventType.SLO_BREACHED)
    inactive = WebhookSubscription(url="http://x", active=False)
    assert not inactive.wants(EventType.INCIDENT_CREATED)
