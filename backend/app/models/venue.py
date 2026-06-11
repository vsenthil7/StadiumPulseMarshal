"""Venue and match models for multi-venue, multi-match operations."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Venue(BaseModel):
    """A tournament venue / host-city stadium."""

    id: str
    name: str
    city: str
    country: str
    capacity: int = Field(gt=0)
    timezone: str = "UTC"


class Match(BaseModel):
    """A scheduled match at a venue."""

    id: str
    venue_id: str
    home: str
    away: str
    kickoff: datetime
    stage: str = "Group"  # Group, Round of 16, etc.

    @property
    def label(self) -> str:
        return f"{self.home} vs {self.away}"


class MatchdayContext(BaseModel):
    """The active operational context: which venue/match is being monitored."""

    venue: Venue
    match: Match
    selected_at: datetime = Field(default_factory=_utcnow)
