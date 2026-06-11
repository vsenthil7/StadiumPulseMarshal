"""Concrete matchday incident scenarios.

Each builds a Scenario with realistic problems, root causes, entities and SLOs.
"""
from __future__ import annotations

from datetime import timedelta

from app.fixtures.scenarios.base import (
    Scenario,
    VENUES,
    default_timeline,
    kickoff_utc,
)
from app.models.domain import Entity, Event, Problem, RootCauseNode
from app.models.enums import EntityType, MatchdayPhase, ProblemStatus, Severity
from app.models.slo import SLI, SLIKind, SLO
from app.models.venue import Match


def _slo(svc_id: str, name: str, kind: SLIKind, target: float) -> SLO:
    return SLO(
        id=f"SLO-{svc_id}-{kind.value}",
        name=name,
        service_id=svc_id,
        sli=SLI(key=f"{svc_id}.{kind.value.lower()}", kind=kind, entity_id=svc_id),
        target=target,
    )


# --- Scenario 1: payment DB saturation (MetLife) -----------------------------
def payment_db_saturation() -> Scenario:
    venue = VENUES["V-METLIFE"]
    kickoff = kickoff_utc(day=13, hour=20)
    tl = default_timeline(kickoff)

    def t(m: int):
        return kickoff + timedelta(minutes=m)

    entities = [
        Entity(id="SVC-PAYMENTS", name="payments-api", type=EntityType.SERVICE,
               tags=["matchday", "tier:critical"], health=62.0),
        Entity(id="DB-PAYMENTS", name="payments-postgres", type=EntityType.DATABASE,
               tags=["matchday", "tier:critical"], health=41.0),
        Entity(id="SVC-TICKETS", name="ticket-scan-api", type=EntityType.SERVICE,
               tags=["matchday", "tier:critical", "gates"], health=98.0),
        Entity(id="SVC-APP", name="fan-app-backend", type=EntityType.APPLICATION,
               tags=["matchday", "tier:high"], health=88.0),
        Entity(id="HOST-EDGE-3", name="edge-node-3", type=EntityType.HOST,
               tags=["edge", "stadium-east"], health=95.0),
    ]
    rc = RootCauseNode(
        entity_id="SVC-PAYMENTS", entity_name="payments-api",
        entity_type=EntityType.SERVICE, confidence=0.34,
        contribution="Elevated response time and error rate observed here first.",
        children=[RootCauseNode(
            entity_id="DB-PAYMENTS", entity_name="payments-postgres",
            entity_type=EntityType.DATABASE, is_root_cause=True, confidence=0.91,
            contribution="Connection pool exhausted at half-time surge; "
                         "max_connections reached, causing upstream timeouts.")],
    )
    primary = Problem(
        id="P-2026-0613-001", title="Payment processing degraded during half-time surge",
        severity=Severity.HIGH, status=ProblemStatus.OPEN, opened_at=t(46),
        affected_entities=[entities[0], entities[1]], root_cause=rc,
        events=[
            Event(id="EV-1", title="Response time degradation", entity_id="SVC-PAYMENTS",
                  timestamp=t(46), description="p95 latency 180ms -> 2,400ms."),
            Event(id="EV-2", title="DB connection pool saturation", entity_id="DB-PAYMENTS",
                  timestamp=t(45), description="Active connections hit max of 100."),
            Event(id="EV-3", title="Error rate increase", entity_id="SVC-PAYMENTS",
                  timestamp=t(47), description="HTTP 5xx rate rose to 12%."),
        ],
        matchday_phase=MatchdayPhase.HALFTIME,
        impact_summary="Concession payments failing for ~12% of fans at half-time; "
                       "queues building at East stand kiosks.",
    )
    secondary = Problem(
        id="P-2026-0613-002", title="Fan app backend elevated latency",
        severity=Severity.MEDIUM, status=ProblemStatus.OPEN, opened_at=t(2),
        affected_entities=[entities[3]],
        events=[Event(id="EV-4", title="Latency increase", entity_id="SVC-APP",
                      timestamp=t(2), description="p90 latency 600ms at kickoff stream surge.")],
        matchday_phase=MatchdayPhase.KICKOFF,
        impact_summary="Fan app live-stats tab slow to load at kickoff.",
    )
    resolved = Problem(
        id="P-2026-0613-000", title="Ticket scan gateway brief timeout",
        severity=Severity.LOW, status=ProblemStatus.RESOLVED, opened_at=t(-88),
        resolved_at=t(-80), affected_entities=[entities[2]], events=[],
        matchday_phase=MatchdayPhase.GATES_OPEN,
        impact_summary="Transient scan delays at gates open; self-recovered.",
    )
    return Scenario(
        key="payment_db_saturation",
        name="Payment DB saturation (MetLife)",
        description="Half-time concession payment failures from DB pool exhaustion.",
        venue=venue, match=Match(id="M-METLIFE", venue_id=venue.id, home="ARG",
                                 away="BRA", kickoff=kickoff, stage="Group"),
        problems=[primary, secondary, resolved], entities=entities, timeline=tl,
        slos=[_slo("SVC-PAYMENTS", "Payments availability", SLIKind.AVAILABILITY, 0.999),
              _slo("SVC-PAYMENTS", "Payments latency", SLIKind.LATENCY, 0.99)],
    )


# --- Scenario 2: CDN edge failure (Azteca) -----------------------------------
def cdn_edge_failure() -> Scenario:
    venue = VENUES["V-AZTECA"]
    kickoff = kickoff_utc(day=17, hour=18)
    tl = default_timeline(kickoff)

    def t(m: int):
        return kickoff + timedelta(minutes=m)

    entities = [
        Entity(id="SVC-STREAM", name="live-stream-edge", type=EntityType.APPLICATION,
               tags=["matchday", "tier:critical", "cdn"], health=55.0),
        Entity(id="HOST-CDN-MX", name="cdn-pop-mexico", type=EntityType.HOST,
               tags=["edge", "cdn"], health=38.0),
    ]
    rc = RootCauseNode(
        entity_id="SVC-STREAM", entity_name="live-stream-edge",
        entity_type=EntityType.APPLICATION, confidence=0.30,
        contribution="Buffering and 5xx spikes on stream start.",
        children=[RootCauseNode(
            entity_id="HOST-CDN-MX", entity_name="cdn-pop-mexico",
            entity_type=EntityType.HOST, is_root_cause=True, confidence=0.88,
            contribution="Regional CDN PoP saturated; origin egress throttled at kickoff.")],
    )
    problem = Problem(
        id="P-AZTECA-001", title="Live stream buffering at kickoff",
        severity=Severity.CRITICAL, status=ProblemStatus.OPEN, opened_at=t(1),
        affected_entities=entities, root_cause=rc,
        events=[Event(id="EV-1", title="5xx spike on stream start", entity_id="SVC-STREAM",
                      timestamp=t(1), description="HTTP 5xx 8% at kickoff.")],
        matchday_phase=MatchdayPhase.KICKOFF,
        impact_summary="In-stadium app live stream buffering for ~30% of fans at kickoff.",
    )
    return Scenario(
        key="cdn_edge_failure",
        name="CDN edge failure (Azteca)",
        description="Kickoff stream buffering from a saturated regional CDN PoP.",
        venue=venue, match=Match(id="M-AZTECA", venue_id=venue.id, home="MEX",
                                 away="GER", kickoff=kickoff, stage="Group"),
        problems=[problem], entities=entities, timeline=tl,
        slos=[_slo("SVC-STREAM", "Stream availability", SLIKind.AVAILABILITY, 0.995)],
    )


# --- Scenario 3: network partition (BC Place) --------------------------------
def network_partition() -> Scenario:
    venue = VENUES["V-BCPLACE"]
    kickoff = kickoff_utc(day=20, hour=22)
    tl = default_timeline(kickoff)

    def t(m: int):
        return kickoff + timedelta(minutes=m)

    entities = [
        Entity(id="SVC-TICKETS", name="ticket-scan-api", type=EntityType.SERVICE,
               tags=["matchday", "tier:critical", "gates"], health=44.0),
        Entity(id="NET-GATE-WEST", name="gate-west-switch", type=EntityType.NETWORK,
               tags=["network", "gates"], health=20.0),
    ]
    rc = RootCauseNode(
        entity_id="SVC-TICKETS", entity_name="ticket-scan-api",
        entity_type=EntityType.SERVICE, confidence=0.40,
        contribution="Scan timeouts concentrated at West gates.",
        children=[RootCauseNode(
            entity_id="NET-GATE-WEST", entity_name="gate-west-switch",
            entity_type=EntityType.NETWORK, is_root_cause=True, confidence=0.86,
            contribution="Network partition: West gate switch dropped uplink during entry surge.")],
    )
    problem = Problem(
        id="P-BCPLACE-001", title="Ticket scanning failing at West gates",
        severity=Severity.HIGH, status=ProblemStatus.OPEN, opened_at=t(-85),
        affected_entities=entities, root_cause=rc,
        events=[Event(id="EV-1", title="Scan timeout surge", entity_id="SVC-TICKETS",
                      timestamp=t(-85), description="Scan timeouts at West gates 22%.")],
        matchday_phase=MatchdayPhase.GATES_OPEN,
        impact_summary="Entry queues building at West gates; scanners failing to validate.",
    )
    return Scenario(
        key="network_partition",
        name="Network partition (BC Place)",
        description="Gate-entry scan failures from a West-gate network partition.",
        venue=venue, match=Match(id="M-BCPLACE", venue_id=venue.id, home="CAN",
                                 away="JPN", kickoff=kickoff, stage="Round of 16"),
        problems=[problem], entities=entities, timeline=tl,
        slos=[_slo("SVC-TICKETS", "Ticket scan availability", SLIKind.AVAILABILITY, 0.999)],
    )


# --- Scenario 4: k8s OOM (MetLife, later match) ------------------------------
def k8s_oom() -> Scenario:
    venue = VENUES["V-METLIFE"]
    kickoff = kickoff_utc(day=25, hour=19)
    tl = default_timeline(kickoff)

    def t(m: int):
        return kickoff + timedelta(minutes=m)

    entities = [
        Entity(id="SVC-APP", name="fan-app-backend", type=EntityType.APPLICATION,
               tags=["matchday", "tier:high"], health=58.0),
        Entity(id="K8S-APP", name="fan-app-deployment", type=EntityType.KUBERNETES,
               tags=["k8s", "matchday"], health=35.0),
    ]
    rc = RootCauseNode(
        entity_id="SVC-APP", entity_name="fan-app-backend",
        entity_type=EntityType.APPLICATION, confidence=0.36,
        contribution="Pod restarts and elevated latency.",
        children=[RootCauseNode(
            entity_id="K8S-APP", entity_name="fan-app-deployment",
            entity_type=EntityType.KUBERNETES, is_root_cause=True, confidence=0.84,
            contribution="OOMKilled pods: memory limit too low for full-time stats surge.")],
    )
    problem = Problem(
        id="P-METLIFE-002", title="Fan app pods OOMKilled at full-time",
        severity=Severity.MEDIUM, status=ProblemStatus.OPEN, opened_at=t(106),
        affected_entities=entities, root_cause=rc,
        events=[Event(id="EV-1", title="OOMKilled", entity_id="K8S-APP",
                      timestamp=t(106), description="3 pods OOMKilled in 2 min.")],
        matchday_phase=MatchdayPhase.FULL_TIME,
        impact_summary="Fan app stats/highlights slow at full-time due to pod restarts.",
    )
    return Scenario(
        key="k8s_oom",
        name="Kubernetes OOM (MetLife)",
        description="Full-time fan-app slowdowns from OOMKilled pods.",
        venue=venue, match=Match(id="M-METLIFE-2", venue_id=venue.id, home="FRA",
                                 away="ESP", kickoff=kickoff, stage="Quarter-final"),
        problems=[problem], entities=entities, timeline=tl,
        slos=[_slo("SVC-APP", "Fan app availability", SLIKind.AVAILABILITY, 0.99)],
    )
