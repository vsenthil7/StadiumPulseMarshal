"""Tests for the remediation store."""
from __future__ import annotations

from app.core.config import Settings
from app.fixtures import matchday
from app.models.enums import RemediationStatus, RiskLevel, Severity
from app.services.remediation import plan_remediations
from app.services.store import RemediationStore


def _actions():
    return plan_remediations(matchday.problems()[0])


def test_register_and_list():
    store = RemediationStore(Settings())
    actions = _actions()
    store.register(actions)
    store.register(actions)  # idempotent setdefault
    assert len(store.list_actions()) == len(actions)
    assert store.get(actions[0].id) is not None
    assert store.get("missing") is None


def test_pending_filters_decided():
    store = RemediationStore(Settings())
    actions = _actions()
    store.register(actions)
    assert len(store.pending()) == len(actions)
    store.decide(actions[0].id, approved=True, decided_by="me")
    assert len(store.pending()) == len(actions) - 1


def test_decide_approve_and_reject_audit():
    store = RemediationStore(Settings())
    actions = _actions()
    store.register(actions)
    d1 = store.decide(actions[0].id, approved=True, decided_by="jane", reason="ok")
    assert d1.approved
    assert store.get(actions[0].id).status == RemediationStatus.APPROVED
    d2 = store.decide(actions[1].id, approved=False, decided_by="jane")
    assert not d2.approved
    assert store.get(actions[1].id).status == RemediationStatus.REJECTED
    assert len(store.audit_log()) == 2


def test_decide_missing_returns_none():
    store = RemediationStore(Settings())
    assert store.decide("nope", approved=True, decided_by="x") is None


def test_auto_approved_status():
    store = RemediationStore(Settings())
    actions = _actions()
    store.register(actions)
    store.decide(actions[0].id, approved=True, decided_by="auto", auto=True)
    assert store.get(actions[0].id).status == RemediationStatus.AUTO_APPROVED


def test_can_auto_approve_disabled_by_default():
    store = RemediationStore(Settings(auto_approve_low_risk=False))
    actions = _actions()
    low = next(a for a in actions if a.risk == RiskLevel.LOW)
    assert store.can_auto_approve(low, Severity.LOW) is False


def test_can_auto_approve_low_risk_within_ceiling():
    store = RemediationStore(
        Settings(auto_approve_low_risk=True, max_auto_approve_severity="MEDIUM")
    )
    actions = _actions()
    low = next(a for a in actions if a.risk == RiskLevel.LOW)
    assert store.can_auto_approve(low, Severity.LOW) is True
    # Above ceiling -> denied
    assert store.can_auto_approve(low, Severity.CRITICAL) is False


def test_can_auto_approve_blocks_non_low_risk():
    store = RemediationStore(Settings(auto_approve_low_risk=True))
    actions = _actions()
    med = next(a for a in actions if a.risk == RiskLevel.MEDIUM)
    assert store.can_auto_approve(med, Severity.LOW) is False


def test_mark_executed():
    store = RemediationStore(Settings())
    actions = _actions()
    store.register(actions)
    assert store.mark_executed(actions[0].id, success=True) is True
    assert store.get(actions[0].id).status == RemediationStatus.EXECUTED
    assert store.mark_executed(actions[1].id, success=False) is True
    assert store.get(actions[1].id).status == RemediationStatus.FAILED
    assert store.mark_executed("missing", success=True) is False
