"""Scenario framework: a Scenario bundles venue, match, problems, entities,
SLOs and timeline for a self-contained matchday situation.

Multiple scenarios are registered (see registry.py) and selectable at runtime,
so the system models more than one incident type and venue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.models.domain import Entity, FixtureTimelineEntry, Problem
from app.models.enums import MatchdayPhase
from app.models.slo import SLO
from app.models.venue import Match, Venue


@dataclass
class Scenario:
    """A fully-described matchday scenario."""

    key: str
    name: str
    description: str
    venue: Venue
    match: Match
    problems: list[Problem] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    slos: list[SLO] = field(default_factory=list)
    timeline: list[FixtureTimelineEntry] = field(default_factory=list)


def default_timeline(kickoff: datetime) -> list[FixtureTimelineEntry]:
    """Standard matchday load curve relative to a kickoff time."""

    def t(m: int) -> datetime:
        return kickoff + timedelta(minutes=m)

    return [
        FixtureTimelineEntry(phase=MatchdayPhase.PRE_GATES, label="Pre-gates",
                             starts_at=t(-120), expected_load_multiplier=0.5),
        FixtureTimelineEntry(phase=MatchdayPhase.GATES_OPEN, label="Gates open",
                             starts_at=t(-90), expected_load_multiplier=3.5),
        FixtureTimelineEntry(phase=MatchdayPhase.KICKOFF, label="Kickoff",
                             starts_at=t(0), expected_load_multiplier=2.0),
        FixtureTimelineEntry(phase=MatchdayPhase.HALFTIME, label="Half-time",
                             starts_at=t(45), expected_load_multiplier=5.0),
        FixtureTimelineEntry(phase=MatchdayPhase.SECOND_HALF, label="Second half",
                             starts_at=t(60), expected_load_multiplier=2.0),
        FixtureTimelineEntry(phase=MatchdayPhase.FULL_TIME, label="Full-time",
                             starts_at=t(105), expected_load_multiplier=4.0),
        FixtureTimelineEntry(phase=MatchdayPhase.POST_MATCH, label="Post-match",
                             starts_at=t(135), expected_load_multiplier=1.5),
    ]


def phase_for(timeline: list[FixtureTimelineEntry], ts: datetime) -> MatchdayPhase:
    current = MatchdayPhase.PRE_GATES
    for entry in timeline:
        if ts >= entry.starts_at:
            current = entry.phase
        else:
            break
    return current


# --- Venue catalogue ---------------------------------------------------------
VENUES: dict[str, Venue] = {
    "V-METLIFE": Venue(id="V-METLIFE", name="MetLife Stadium",
                       city="East Rutherford", country="USA", capacity=82500,
                       timezone="America/New_York"),
    "V-AZTECA": Venue(id="V-AZTECA", name="Estadio Azteca", city="Mexico City",
                      country="Mexico", capacity=87523, timezone="America/Mexico_City"),
    "V-BCPLACE": Venue(id="V-BCPLACE", name="BC Place", city="Vancouver",
                       country="Canada", capacity=54500, timezone="America/Vancouver"),
}


def kickoff_utc(*, day: int, hour: int) -> datetime:
    return datetime(2026, 6, day, hour, 0, tzinfo=timezone.utc)
