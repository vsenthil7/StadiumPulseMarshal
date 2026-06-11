"""Unit tests for Phase 3 services."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.events.bus import DomainEvent, EventBus, EventType
from app.models.domain import Problem
from app.models.enums import ProblemStatus, Severity
from app.models.incident import (
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentState,
)
from app.models.slo import BurnState, ErrorBudget
from app.models.webhook import WebhookSubscription
from app.observability.metrics import reset_metrics
from app.repositories.memory.repositories import (
    MemoryIncidentRepository,
    MemoryNotificationRepository,
)
from app.services.escalation_engine import EscalationEngine
from app.services.incident_service import IncidentService
from app.services.notification_service import NotificationService
from app.services.postmortem import generate_postmortem
from app.services.slo_history import SLOHistory
from app.services.webhook_service import WebhookDispatcher, WebhookRepository


def _budget(slo_id: str, burn: float, state: BurnState) -> ErrorBudget:
    return ErrorBudget(
        slo_id=slo_id, slo_name=f"name-{slo_id}", target=0.99, achieved=0.99,
        consumed_fraction=0.5, remaining_fraction=0.5, burn_rate=burn,
        state=state,
    )


# --- SLO history ---
def test_slo_history_trend_directions():
    h = SLOHistory()
    assert h.trend("none") is None
    # worsening: burn rate rising
    h.record([_budget("S", 1.0, BurnState.SLOW_BURN)])
    h.record([_budget("S", 3.0, BurnState.FAST_BURN)])
    t = h.trend("S")
    assert t.direction == "worsening"
    assert t.max_burn_rate == 3.0
    assert t.samples == 2
    # improving
    h2 = SLOHistory()
    h2.record([_budget("S", 3.0, BurnState.FAST_BURN)])
    h2.record([_budget("S", 1.0, BurnState.SLOW_BURN)])
    assert h2.trend("S").direction == "improving"
    # stable (single sample)
    h3 = SLOHistory()
    h3.record([_budget("S", 1.0, BurnState.SLOW_BURN)])
    assert h3.trend("S").direction == "stable"


def test_slo_history_all_trends():
    h = SLOHistory()
    h.record([_budget("A", 1.0, BurnState.HEALTHY), _budget("B", 2.0, BurnState.FAST_BURN)])
    trends = h.all_trends()
    assert len(trends) == 2


def test_slo_history_ring_buffer():
    h = SLOHistory(max_per_slo=3)
    for r in range(5):
        h.record([_budget("S", float(r), BurnState.HEALTHY)])
    assert h.trend("S").samples == 3


# --- postmortem ---
def _resolved_incident() -> Incident:
    now = datetime.now(timezone.utc)
    inc = Incident(
        id="INC-1", problem_id="P", title="Payment outage",
        severity=Severity.HIGH, state=IncidentState.RESOLVED,
        created_at=now - timedelta(minutes=12),
        acknowledged_at=now - timedelta(minutes=10),
        resolved_at=now, impact_summary="12% of payments failing",
        remediation_ids=["RA-1"],
    )
    inc.add_event(IncidentEvent(type=IncidentEventType.CREATED, detail="opened"))
    inc.add_event(IncidentEvent(type=IncidentEventType.ESCALATED, detail="to T2"))
    inc.add_event(IncidentEvent(type=IncidentEventType.STATE_CHANGE,
                                detail="RESOLVED"))
    return inc


def test_postmortem_generation():
    pm = generate_postmortem(_resolved_incident())
    assert pm.incident_id == "INC-1"
    assert pm.ttr_minutes is not None
    assert pm.tta_minutes is not None
    assert "RA-1" in pm.remediation_ids
    assert pm.markdown.startswith("# Postmortem")
    assert "Timeline" in pm.markdown
    assert "Remediations applied" in pm.markdown
    assert "Escalated 1 time" in pm.summary


def test_postmortem_minimal_incident():
    inc = Incident(id="I", problem_id="P", title="t", severity=Severity.LOW)
    pm = generate_postmortem(inc)
    assert pm.ttr_minutes is None
    assert pm.final_state == "DETECTED"


# --- webhook service ---
async def test_webhook_repo_crud():
    repo = WebhookRepository()
    sub = WebhookSubscription(url="http://x/hook")
    repo.add(sub)
    assert repo.get(sub.id) is not None
    assert len(repo.list()) == 1
    assert repo.delete(sub.id) is True
    assert repo.delete("missing") is False


async def test_webhook_dispatcher_delivers_and_records():
    reset_metrics()
    repo = WebhookRepository()
    repo.add(WebhookSubscription(
        url="http://hook.test/ok", event_types=[EventType.INCIDENT_CREATED]))
    repo.add(WebhookSubscription(
        url="http://hook.test/fail", event_types=[EventType.INCIDENT_CREATED]))

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/ok":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(500)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(repo, http)
    bus = EventBus()
    dispatcher.register(bus)
    await bus.publish(DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="I1"))
    statuses = sorted(
        (s.last_status for s in repo.list()), key=lambda x: x or 0
    )
    assert 200 in statuses
    # the failing one recorded a failure
    assert any(s.failure_count == 1 for s in repo.list())


async def test_webhook_dispatcher_skips_unsubscribed():
    repo = WebhookRepository()
    repo.add(WebhookSubscription(
        url="http://hook.test/x", event_types=[EventType.SLO_BREACHED]))
    called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(repo, http)
    await dispatcher.on_event(
        DomainEvent(type=EventType.INCIDENT_CREATED, subject_id="I1")
    )
    assert called["n"] == 0


async def test_webhook_dispatcher_network_exception():
    reset_metrics()
    repo = WebhookRepository()
    repo.add(WebhookSubscription(url="http://unreachable/hook"))

    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(repo, http)
    await dispatcher.on_event(DomainEvent(type=EventType.INCIDENT_CREATED))
    assert repo.list()[0].failure_count == 1
    assert repo.list()[0].last_status is None


# --- incident search & bulk ---
def _svc() -> IncidentService:
    return IncidentService(
        MemoryIncidentRepository(),
        EscalationEngine([], []),
        NotificationService(MemoryNotificationRepository()),
        events=EventBus(),
    )


async def test_incident_search_filters():
    svc = _svc()
    await svc.create_from_problem(
        Problem(id="P1", title="Payment outage", severity=Severity.HIGH,
                status=ProblemStatus.OPEN, impact_summary="kiosks"),
        venue_id="V1")
    await svc.create_from_problem(
        Problem(id="P2", title="Stream buffering", severity=Severity.MEDIUM,
                status=ProblemStatus.OPEN), venue_id="V2")
    by_sev, total = await svc.search(severity=Severity.HIGH)
    assert total == 1 and by_sev[0].title == "Payment outage"
    by_text, t2 = await svc.search(text="stream")
    assert t2 == 1
    by_state, t3 = await svc.search(state=IncidentState.DETECTED)
    assert t3 == 2
    by_venue, t4 = await svc.search(venue_id="V1")
    assert t4 == 1
    paged, t5 = await svc.search(offset=1, limit=1)
    assert t5 == 2 and len(paged) == 1


async def test_incident_bulk_transition_partial():
    svc = _svc()
    inc = await svc.create_from_problem(
        Problem(id="P1", title="t", severity=Severity.HIGH,
                status=ProblemStatus.OPEN))
    result = await svc.bulk_transition(
        [inc.id, "MISSING"], IncidentState.ACKNOWLEDGED, actor="jane")
    assert inc.id in result["succeeded"]
    assert "MISSING" in result["failed"]
