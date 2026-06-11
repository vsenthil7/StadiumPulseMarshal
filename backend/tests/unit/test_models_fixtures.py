"""Tests for domain models, fixtures and remediation planning."""
from __future__ import annotations

from datetime import timedelta

from app.fixtures import matchday
from app.models.domain import Metric, MetricPoint, Problem, RootCauseNode
from app.models.enums import EntityType, MatchdayPhase, ProblemStatus, Severity
from app.services.remediation import plan_remediations


def test_metric_latest_empty_and_filled():
    m = Metric(key="k", unit="ms", entity_id="e")
    assert m.latest is None
    m2 = Metric(
        key="k",
        unit="ms",
        entity_id="e",
        points=[
            MetricPoint(timestamp=matchday.KICKOFF, value=1.0),
            MetricPoint(timestamp=matchday.KICKOFF, value=2.0),
        ],
    )
    assert m2.latest == 2.0


def test_problem_is_open():
    p = Problem(id="p", title="t", severity=Severity.LOW, status=ProblemStatus.OPEN)
    assert p.is_open
    p2 = Problem(
        id="p", title="t", severity=Severity.LOW, status=ProblemStatus.RESOLVED
    )
    assert not p2.is_open


def test_fixtures_problems_and_entities():
    probs = matchday.problems()
    assert len(probs) == 3
    assert any(p.is_open for p in probs)
    assert len(matchday.entities()) == 5


def test_fixtures_metrics_branches():
    assert matchday.metrics_for("DB-PAYMENTS")[0].key == "db.connections.active"
    assert matchday.metrics_for("SVC-PAYMENTS")[0].key == "service.response.time.p95"
    other = matchday.metrics_for("SVC-APP")
    assert other[0].latest == 120.0


def test_phase_for_resolution():
    assert matchday.phase_for(matchday.KICKOFF - timedelta(hours=3)) == (
        MatchdayPhase.PRE_GATES
    )
    assert matchday.phase_for(matchday.KICKOFF + timedelta(minutes=46)) == (
        MatchdayPhase.HALFTIME
    )
    assert matchday.phase_for(matchday.KICKOFF + timedelta(minutes=200)) == (
        MatchdayPhase.POST_MATCH
    )


def test_plan_remediations_database_root():
    p = matchday.problems()[0]
    actions = plan_remediations(p)
    assert len(actions) == 2
    assert "connection pool" in actions[0].title.lower()


def test_plan_remediations_service_root():
    rc = RootCauseNode(
        entity_id="SVC",
        entity_name="svc",
        entity_type=EntityType.SERVICE,
        is_root_cause=True,
        confidence=0.8,
    )
    p = Problem(
        id="p",
        title="t",
        severity=Severity.HIGH,
        status=ProblemStatus.OPEN,
        root_cause=rc,
    )
    actions = plan_remediations(p)
    assert "scale-out" in actions[0].title.lower()


def test_plan_remediations_no_root_cause_escalates():
    p = Problem(id="p", title="t", severity=Severity.HIGH, status=ProblemStatus.OPEN)
    actions = plan_remediations(p)
    assert "escalate" in actions[0].title.lower()


def test_plan_remediations_descends_to_flagged_child():
    # root not flagged, child flagged as DB
    child = RootCauseNode(
        entity_id="DB",
        entity_name="db",
        entity_type=EntityType.DATABASE,
        is_root_cause=True,
        confidence=0.9,
    )
    parent = RootCauseNode(
        entity_id="SVC",
        entity_name="svc",
        entity_type=EntityType.SERVICE,
        is_root_cause=False,
        children=[child],
    )
    p = Problem(
        id="p",
        title="t",
        severity=Severity.HIGH,
        status=ProblemStatus.OPEN,
        root_cause=parent,
    )
    actions = plan_remediations(p)
    assert "connection pool" in actions[0].title.lower()
