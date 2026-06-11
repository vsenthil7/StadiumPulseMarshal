"""Schemas for the expanded API surface (Phase 2)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.incident import Incident, IncidentState
from app.models.notification import Notification
from app.models.slo import ErrorBudget
from app.services.analytics import AnalyticsSummary


class Page(BaseModel):
    """Pagination envelope."""

    total: int
    offset: int
    limit: int


class IncidentListResponse(BaseModel):
    incidents: list[Incident]
    page: Page


class IncidentResponse(BaseModel):
    incident: Incident


class CreateIncidentRequest(BaseModel):
    problem_id: str
    venue_id: str | None = None
    match_id: str | None = None


class TransitionRequest(BaseModel):
    target: IncidentState
    actor: str = "sre-operator"
    note: str = ""


class AssignRequest(BaseModel):
    assignee: str
    actor: str = "sre-operator"


class NoteRequest(BaseModel):
    note: str
    actor: str = "sre-operator"


class SLOListResponse(BaseModel):
    budgets: list[ErrorBudget]


class AnalyticsResponse(BaseModel):
    summary: AnalyticsSummary


class NotificationListResponse(BaseModel):
    notifications: list[Notification]


class ScenarioInfo(BaseModel):
    key: str
    name: str
    description: str
    venue: str
    match: str
    severity: str


class ScenarioListResponse(BaseModel):
    scenarios: list[ScenarioInfo]
    active: str


class SelectScenarioRequest(BaseModel):
    key: str
