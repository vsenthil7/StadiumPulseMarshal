"""Realistic matchday incident fixtures for the mock data path.

Models a 2026 World Cup match at a host-city stadium. The scenario centres on a
half-time payment-gateway degradation caused by a downstream database connection
pool saturation — exactly the kind of causally-localised problem Davis AI
surfaces and the agent then correlates with the match timeline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.domain import (
    Entity,
    Event,
    FixtureTimelineEntry,
    Metric,
    MetricPoint,
    Problem,
    RootCauseNode,
)
from app.models.enums import (
    EntityType,
    MatchdayPhase,
    ProblemStatus,
    Severity,
)

# Anchor the scenario to a fixed kickoff so timelines are deterministic.
KICKOFF = datetime(2026, 6, 13, 20, 0, tzinfo=timezone.utc)


def _t(minutes: int) -> datetime:
    return KICKOFF + timedelta(minutes=minutes)


# --- Entities ----------------------------------------------------------------
ENTITIES: dict[str, Entity] = {
    "SVC-PAYMENTS": Entity(
        id="SVC-PAYMENTS",
        name="payments-api",
        type=EntityType.SERVICE,
        tags=["matchday", "tier:critical", "concessions"],
        health=62.0,
    ),
    "SVC-TICKETS": Entity(
        id="SVC-TICKETS",
        name="ticket-scan-api",
        type=EntityType.SERVICE,
        tags=["matchday", "tier:critical", "gates"],
        health=98.0,
    ),
    "SVC-APP": Entity(
        id="SVC-APP",
        name="fan-app-backend",
        type=EntityType.APPLICATION,
        tags=["matchday", "tier:high"],
        health=88.0,
    ),
    "DB-PAYMENTS": Entity(
        id="DB-PAYMENTS",
        name="payments-postgres",
        type=EntityType.DATABASE,
        tags=["matchday", "tier:critical"],
        health=41.0,
    ),
    "HOST-EDGE-3": Entity(
        id="HOST-EDGE-3",
        name="edge-node-3",
        type=EntityType.HOST,
        tags=["edge", "stadium-east"],
        health=95.0,
    ),
}


# --- Fixture timeline --------------------------------------------------------
def fixture_timeline() -> list[FixtureTimelineEntry]:
    return [
        FixtureTimelineEntry(
            phase=MatchdayPhase.PRE_GATES,
            label="Pre-gates",
            starts_at=_t(-120),
            expected_load_multiplier=0.5,
        ),
        FixtureTimelineEntry(
            phase=MatchdayPhase.GATES_OPEN,
            label="Gates open",
            starts_at=_t(-90),
            expected_load_multiplier=3.5,
        ),
        FixtureTimelineEntry(
            phase=MatchdayPhase.KICKOFF,
            label="Kickoff",
            starts_at=_t(0),
            expected_load_multiplier=2.0,
        ),
        FixtureTimelineEntry(
            phase=MatchdayPhase.HALFTIME,
            label="Half-time",
            starts_at=_t(45),
            expected_load_multiplier=5.0,
        ),
        FixtureTimelineEntry(
            phase=MatchdayPhase.SECOND_HALF,
            label="Second half",
            starts_at=_t(60),
            expected_load_multiplier=2.0,
        ),
        FixtureTimelineEntry(
            phase=MatchdayPhase.FULL_TIME,
            label="Full-time",
            starts_at=_t(105),
            expected_load_multiplier=4.0,
        ),
        FixtureTimelineEntry(
            phase=MatchdayPhase.POST_MATCH,
            label="Post-match",
            starts_at=_t(135),
            expected_load_multiplier=1.5,
        ),
    ]


def phase_for(ts: datetime) -> MatchdayPhase:
    """Resolve which matchday phase a timestamp falls in."""
    current = MatchdayPhase.PRE_GATES
    for entry in fixture_timeline():
        if ts >= entry.starts_at:
            current = entry.phase
        else:
            break
    return current


# --- Root cause tree ---------------------------------------------------------
def _root_cause() -> RootCauseNode:
    return RootCauseNode(
        entity_id="SVC-PAYMENTS",
        entity_name="payments-api",
        entity_type=EntityType.SERVICE,
        is_root_cause=False,
        confidence=0.34,
        contribution="Elevated response time and error rate observed here first.",
        children=[
            RootCauseNode(
                entity_id="DB-PAYMENTS",
                entity_name="payments-postgres",
                entity_type=EntityType.DATABASE,
                is_root_cause=True,
                confidence=0.91,
                contribution=(
                    "Connection pool exhausted at half-time surge; "
                    "max_connections reached, causing upstream timeouts."
                ),
            )
        ],
    )


# --- Events ------------------------------------------------------------------
def _events() -> list[Event]:
    return [
        Event(
            id="EV-1",
            title="Response time degradation",
            entity_id="SVC-PAYMENTS",
            timestamp=_t(46),
            description="p95 latency rose from 180ms to 2,400ms.",
        ),
        Event(
            id="EV-2",
            title="Database connection pool saturation",
            entity_id="DB-PAYMENTS",
            timestamp=_t(45),
            description="Active connections hit configured max of 100.",
        ),
        Event(
            id="EV-3",
            title="Error rate increase",
            entity_id="SVC-PAYMENTS",
            timestamp=_t(47),
            description="HTTP 5xx rate rose to 12%.",
        ),
    ]


# --- Problems ----------------------------------------------------------------
def problems() -> list[Problem]:
    primary = Problem(
        id="P-2026-0613-001",
        title="Payment processing degraded during half-time surge",
        severity=Severity.HIGH,
        status=ProblemStatus.OPEN,
        opened_at=_t(46),
        affected_entities=[
            ENTITIES["SVC-PAYMENTS"],
            ENTITIES["DB-PAYMENTS"],
        ],
        root_cause=_root_cause(),
        events=_events(),
        matchday_phase=MatchdayPhase.HALFTIME,
        impact_summary=(
            "Concession payments failing for ~12% of fans at half-time; "
            "queues building at East stand kiosks."
        ),
    )
    secondary = Problem(
        id="P-2026-0613-002",
        title="Fan app backend elevated latency",
        severity=Severity.MEDIUM,
        status=ProblemStatus.OPEN,
        opened_at=_t(2),
        affected_entities=[ENTITIES["SVC-APP"]],
        events=[
            Event(
                id="EV-4",
                title="Latency increase",
                entity_id="SVC-APP",
                timestamp=_t(2),
                description="p90 latency 600ms at kickoff stream surge.",
            )
        ],
        matchday_phase=MatchdayPhase.KICKOFF,
        impact_summary="Fan app live-stats tab slow to load at kickoff.",
    )
    resolved = Problem(
        id="P-2026-0613-000",
        title="Ticket scan gateway brief timeout",
        severity=Severity.LOW,
        status=ProblemStatus.RESOLVED,
        opened_at=_t(-88),
        resolved_at=_t(-80),
        affected_entities=[ENTITIES["SVC-TICKETS"]],
        events=[],
        matchday_phase=MatchdayPhase.GATES_OPEN,
        impact_summary="Transient scan delays at gates open; self-recovered.",
    )
    return [primary, secondary, resolved]


def entities() -> list[Entity]:
    return list(ENTITIES.values())


def metrics_for(entity_id: str) -> list[Metric]:
    """Synthetic metric series; payments DB shows the saturation spike."""
    base = _t(40)
    if entity_id == "DB-PAYMENTS":
        pts = [
            MetricPoint(timestamp=base + timedelta(minutes=i), value=v)
            for i, v in enumerate([45, 60, 88, 100, 100, 100, 98])
        ]
        return [Metric(key="db.connections.active", unit="count",
                       entity_id=entity_id, points=pts)]
    if entity_id == "SVC-PAYMENTS":
        pts = [
            MetricPoint(timestamp=base + timedelta(minutes=i), value=v)
            for i, v in enumerate([180, 240, 900, 2400, 2200, 1800, 700])
        ]
        return [Metric(key="service.response.time.p95", unit="ms",
                       entity_id=entity_id, points=pts)]
    return [
        Metric(
            key="service.response.time.p95",
            unit="ms",
            entity_id=entity_id,
            points=[MetricPoint(timestamp=base, value=120.0)],
        )
    ]
