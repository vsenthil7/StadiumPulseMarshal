"""Postmortem workflow — blameless incident review with timeline + actions."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostmortemStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"


class TimelineEntry(BaseModel):
    at: datetime
    text: str
    author: str = ""


class ActionItem(BaseModel):
    id: str
    description: str
    owner: str = ""
    due: str | None = None
    done: bool = False


class Postmortem(BaseModel):
    id: str = ""
    incident_id: str | None = None
    title: str
    status: PostmortemStatus = PostmortemStatus.DRAFT
    severity: str = ""
    summary: str = ""
    root_cause: str = ""
    impact: str = ""
    lessons: str = ""
    timeline: list[TimelineEntry] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    venue_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    created_by: str = ""
