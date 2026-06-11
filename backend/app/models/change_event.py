"""Change-event correlation — deployments/config changes linked to incidents."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChangeType(str, Enum):
    DEPLOYMENT = "deployment"
    CONFIG = "config"
    INFRA = "infra"
    FEATURE_FLAG = "feature_flag"
    ROLLBACK = "rollback"


class ChangeEvent(BaseModel):
    id: str = ""
    change_type: ChangeType = ChangeType.DEPLOYMENT
    title: str
    service_id: str = ""
    venue_id: str | None = None
    actor: str = ""
    at: datetime = Field(default_factory=_utcnow)
    metadata: dict = Field(default_factory=dict)
    # Incidents this change is correlated with (by proximity / manual link).
    linked_incident_ids: list[str] = Field(default_factory=list)
