"""Runbook library — versioned, tagged, RBAC-protected procedure definitions."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunbookCategory(str, Enum):
    INCIDENT = "incident"
    DEPLOYMENT = "deployment"
    SCALING = "scaling"
    DATABASE = "database"
    NETWORK = "network"
    SECURITY = "security"
    CUSTOM = "custom"


class RunbookStep(BaseModel):
    order: int
    title: str
    description: str
    command: str | None = None
    automation_ref: str | None = None
    verification: str | None = None
    rollback: str | None = None


class Runbook(BaseModel):
    id: str = ""
    name: str
    category: RunbookCategory = RunbookCategory.INCIDENT
    version: int = 1
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    steps: list[RunbookStep] = Field(default_factory=list)
    owner: str = ""
    venue_ids: list[str] = Field(default_factory=list)
    automation_catalog_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    created_by: str = ""


class RunbookExecution(BaseModel):
    id: str
    runbook_id: str
    incident_id: str | None = None
    actor: str
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
    status: str = "running"  # running | completed | failed | aborted
    step_results: list[dict[str, Any]] = Field(default_factory=list)
    dispatch_result: dict[str, Any] | None = None
