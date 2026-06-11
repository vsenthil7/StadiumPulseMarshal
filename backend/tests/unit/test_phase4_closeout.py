"""Closeout tests for the final Phase 4 coverage branches."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.events.bus import DomainEvent, EventBus, EventType
from app.middleware.tracing import get_span_id, get_trace_id
from app.models.audit import AuditEntry
from app.models.outbox import OutboxEntry
from app.models.webhook import WebhookSubscription
from app.repositories.factory import build_repositories
from app.services.outbox_relay import OutboxRelay
from app.services.webhook_service import WebhookDispatcher, WebhookRepository


def test_trace_span_accessors_default():
    # Default context values when no middleware has run.
    assert isinstance(get_trace_id(), str)
    assert isinstance(get_span_id(), str)


async def test_memory_audit_action_filter_skips():
    from app.repositories.memory.repositories import MemoryAuditLogRepository

    repo = MemoryAuditLogRepository()
    await repo.add(AuditEntry(actor="a", action="create", resource_type="r",
                              resource_id="1"))
    await repo.add(AuditEntry(actor="a", action="delete", resource_type="r",
                              resource_id="2"))
    # action filter excludes the non-matching one (covers the continue)
    res = await repo.query(action="create")
    assert len(res) == 1 and res[0].resource_id == "1"
    # resource_id filter excludes non-matching (covers that continue too)
    res_rid = await repo.query(resource_id="2")
    assert len(res_rid) == 1 and res_rid[0].action == "delete"
    # resource_type filter mismatch
    assert len(await repo.query(resource_type="other")) == 0


@pytest.fixture
async def sql_repos(tmp_path):
    bundle = build_repositories(
        Settings(database_url=f"sqlite+aiosqlite:///{tmp_path}/cov.db")
    )
    await bundle.init()
    yield bundle
    await bundle.dispose()


async def test_sql_outbox_repo(sql_repos):
    repo = sql_repos.outbox
    e = OutboxEntry.from_event(
        DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="I1"))
    await repo.add(e)
    pending = await repo.list_pending()
    assert len(pending) == 1
    await repo.mark_dispatched(e.id)
    assert len(await repo.list_pending()) == 0
    assert len(await repo.list_all()) == 1
    # mark_failed path
    e2 = OutboxEntry.from_event(DomainEvent(type=EventType.SLO_BREACHED))
    await repo.add(e2)
    await repo.mark_failed(e2.id, "boom")
    all_entries = await repo.list_all()
    failed = [x for x in all_entries if x.id == e2.id][0]
    assert failed.attempts == 1 and failed.last_error == "boom"
    # mark on missing id: no-op (no exception)
    await repo.mark_dispatched("missing")
    await repo.mark_failed("missing", "x")


async def test_sql_audit_repo_filters(sql_repos):
    repo = sql_repos.audit_log
    await repo.add(AuditEntry(actor="jane", action="create",
                              resource_type="incident", resource_id="I1"))
    await repo.add(AuditEntry(actor="sam", action="transition",
                              resource_type="incident", resource_id="I1"))
    assert await repo.count() == 2
    assert len(await repo.query(actor="jane")) == 1
    assert len(await repo.query(action="transition")) == 1
    assert len(await repo.query(resource_type="incident")) == 2
    assert len(await repo.query(resource_id="I2")) == 0
    first = await repo.query(limit=1)
    after = await repo.query(after_cursor=first[-1].id, limit=10)
    assert all(e.id > first[-1].id for e in after)


async def test_outbox_relay_loop_runs():
    repo = build_repositories(Settings()).outbox
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(None, lambda ev: seen.append(ev.subject_id) or _noop())
    await repo.add(OutboxEntry.from_event(
        DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="X")))
    relay = OutboxRelay(repo, bus, poll_interval=0.01)
    relay.start()
    # let the loop tick at least once
    await asyncio.sleep(0.05)
    await relay.stop()
    assert "X" in seen


def _noop():
    return None


async def test_webhook_redrive_with_event_redelivers():
    repo = WebhookRepository()
    sub = WebhookSubscription(url="http://hook/ok")
    sub.dead_lettered = True
    repo.add(sub)
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return httpx.Response(200)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    d = WebhookDispatcher(repo, http)
    out = await d.redrive(
        sub.id, DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="I1"))
    assert out is not None
    assert out.dead_lettered is False
    assert calls["n"] == 1
    # redrive missing returns None
    assert await d.redrive("missing") is None
