"""Unit tests for Phase 4 modules (outbox, audit, idempotency, tracing, config)."""
from __future__ import annotations

import httpx
import pytest

from app.core.config import ConfigurationError, Settings
from app.events.bus import DomainEvent, EventBus, EventType
from app.middleware.tracing import (
    format_traceparent,
    parse_traceparent,
)
from app.models.audit import AuditEntry, new_audit_id
from app.models.outbox import OutboxEntry, OutboxStatus
from app.repositories.memory.repositories import (
    MemoryAuditLogRepository,
    MemoryOutboxRepository,
)
from app.services.audit_service import AuditService
from app.services.idempotency import IdempotencyStore
from app.services.outbox_relay import OutboxRelay


# --- outbox model + repo + relay ---
def test_outbox_entry_roundtrip():
    ev = DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="I1",
                     payload={"x": 1})
    entry = OutboxEntry.from_event(ev)
    assert entry.status == OutboxStatus.PENDING
    back = entry.to_event()
    assert back.type == EventType.INCIDENT_CREATED
    assert back.subject_id == "I1"
    assert back.payload == {"x": 1}


async def test_memory_outbox_lifecycle():
    repo = MemoryOutboxRepository()
    e = OutboxEntry.from_event(DomainEvent(type=EventType.SLO_BREACHED))
    await repo.add(e)
    assert len(await repo.list_pending()) == 1
    await repo.mark_dispatched(e.id)
    assert len(await repo.list_pending()) == 0
    assert len(await repo.list_all()) == 1
    # mark_failed on a fresh pending entry
    e2 = OutboxEntry.from_event(DomainEvent(type=EventType.SLO_BREACHED))
    await repo.add(e2)
    await repo.mark_failed(e2.id, "boom")
    all_entries = await repo.list_all()
    failed = [x for x in all_entries if x.id == e2.id][0]
    assert failed.status == OutboxStatus.FAILED
    assert failed.attempts == 1
    # mark on missing id is a no-op
    await repo.mark_dispatched("missing")
    await repo.mark_failed("missing", "x")


async def test_outbox_relay_drains():
    repo = MemoryOutboxRepository()
    bus = EventBus()
    seen: list[str] = []

    async def handler(ev: DomainEvent) -> None:
        seen.append(ev.subject_id)

    bus.subscribe(None, handler)
    await repo.add(OutboxEntry.from_event(
        DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="A")))
    await repo.add(OutboxEntry.from_event(
        DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="B")))
    relay = OutboxRelay(repo, bus)
    delivered = await relay.drain_once()
    assert delivered == 2
    assert set(seen) == {"A", "B"}
    assert len(await repo.list_pending()) == 0


async def test_outbox_relay_start_no_loop_noop():
    # Constructed/stopped without a running loop manager started: start() is a
    # no-op when called outside a loop is covered indirectly; here ensure stop()
    # on a never-started relay is safe.
    relay = OutboxRelay(MemoryOutboxRepository(), EventBus())
    await relay.stop()  # no task → safe


async def test_outbox_relay_start_stop_in_loop():
    relay = OutboxRelay(MemoryOutboxRepository(), EventBus(), poll_interval=0.01)
    relay.start()  # running loop present (pytest-asyncio)
    relay.start()  # idempotent second start
    await relay.stop()


# --- audit ---
def test_audit_id_is_sortable():
    a = new_audit_id()
    b = new_audit_id()
    # time-prefixed, so later id sorts after earlier
    assert a <= b or a[:13] <= b[:13]


async def test_audit_service_record_and_query():
    svc = AuditService(MemoryAuditLogRepository())
    await svc.record(actor="jane", action="incident.create",
                     resource_type="incident", resource_id="I1",
                     after={"state": "DETECTED"})
    await svc.record(actor="sam", action="incident.transition",
                     resource_type="incident", resource_id="I1",
                     before={"state": "DETECTED"}, after={"state": "ACKNOWLEDGED"})
    assert await svc.count() == 2
    by_actor = await svc.query(actor="jane")
    assert len(by_actor) == 1
    by_action = await svc.query(action="incident.transition")
    assert len(by_action) == 1
    by_res = await svc.query(resource_id="I1")
    assert len(by_res) == 2
    by_type = await svc.query(resource_type="nonexistent")
    assert len(by_type) == 0


async def test_audit_cursor_pagination():
    repo = MemoryAuditLogRepository()
    svc = AuditService(repo)
    for i in range(5):
        await svc.record(actor="a", action="act", resource_type="r",
                         resource_id=f"R{i}")
    first = await svc.query(limit=2)
    assert len(first) == 2
    after = await svc.query(after_cursor=first[-1].id, limit=2)
    assert len(after) == 2
    # no overlap
    assert {e.id for e in first}.isdisjoint({e.id for e in after})


# --- idempotency ---
def test_idempotency_store():
    store = IdempotencyStore()
    assert store.get("ns", "k1") is None
    store.put("ns", "k1", 201, {"incident": {"id": "I1"}})
    cached = store.get("ns", "k1")
    assert cached["status_code"] == 201
    assert cached["body"]["incident"]["id"] == "I1"
    # namespacing prevents collision
    assert store.get("other", "k1") is None
    assert len(store) == 1


def test_idempotency_capacity_eviction():
    store = IdempotencyStore(capacity=2)
    store.put("ns", "a", 200, {})
    store.put("ns", "b", 200, {})
    store.put("ns", "c", 200, {})  # evicts "a" (LRU)
    assert store.get("ns", "a") is None
    assert store.get("ns", "b") is not None
    assert store.get("ns", "c") is not None


# --- tracing ---
def test_parse_traceparent_valid():
    tid = "0af7651916cd43dd8448eb211c80319c"
    sid = "b7ad6b7169203331"
    parsed = parse_traceparent(f"00-{tid}-{sid}-01")
    assert parsed == (tid, sid)


def test_parse_traceparent_invalid():
    assert parse_traceparent(None) is None
    assert parse_traceparent("garbage") is None
    # all-zero trace id rejected
    assert parse_traceparent(f"00-{'0'*32}-{'1'*16}-01") is None
    # all-zero span id rejected
    assert parse_traceparent(f"00-{'1'*32}-{'0'*16}-01") is None


def test_format_traceparent():
    tp = format_traceparent("a" * 32, "b" * 16, sampled=True)
    assert tp == f"00-{'a'*32}-{'b'*16}-01"
    assert format_traceparent("a" * 32, "b" * 16, sampled=False).endswith("-00")


# --- config self-check ---
def test_config_validate_ok_mock_mode():
    assert Settings(use_mocks=True).validate_for_startup() == []


def test_config_validate_auth_without_secret():
    problems = Settings(use_mocks=True, auth_enabled=True).validate_for_startup()
    assert any("AUTH_ENABLED" in p for p in problems)


def test_config_validate_live_without_backend():
    problems = Settings(use_mocks=False).validate_for_startup()
    assert any("USE_MOCKS is false" in p for p in problems)


def test_config_validate_bad_rate_limit_and_webhook():
    problems = Settings(
        use_mocks=True, rate_limit_enabled=True, rate_limit_per_minute=0,
        webhook_timeout_seconds=0,
    ).validate_for_startup()
    assert any("RATE_LIMIT_PER_MINUTE" in p for p in problems)
    assert any("WEBHOOK_TIMEOUT_SECONDS" in p for p in problems)


def test_configuration_error_is_runtime_error():
    assert issubclass(ConfigurationError, RuntimeError)
