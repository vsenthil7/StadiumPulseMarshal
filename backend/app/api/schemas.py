"""API request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.domain import (
    AgentAnalysis,
    ApprovalDecision,
    Entity,
    FixtureTimelineEntry,
    Problem,
    RemediationAction,
)


class ConfigResponse(BaseModel):
    app_name: str
    app_version: str
    data_source: str
    dynatrace_live: bool
    gemini_live: bool
    agent_backend: str
    auto_approve_low_risk: bool


class HealthResponse(BaseModel):
    status: str = "ok"


class ProblemList(BaseModel):
    problems: list[Problem]


class EntityList(BaseModel):
    entities: list[Entity]


class TimelineResponse(BaseModel):
    timeline: list[FixtureTimelineEntry]


class AnalyzeResponse(BaseModel):
    analysis: AgentAnalysis


class RemediationList(BaseModel):
    actions: list[RemediationAction]


class DecisionRequest(BaseModel):
    decided_by: str = Field(default="sre-operator")
    reason: str = Field(default="")


class DecisionResponse(BaseModel):
    decision: ApprovalDecision
    action: RemediationAction


class AuditResponse(BaseModel):
    decisions: list[ApprovalDecision]


class ExecuteResponse(BaseModel):
    action: RemediationAction
    executed: bool
    dispatch: dict | None = None


class SettingsUpdate(BaseModel):
    auto_approve_low_risk: bool | None = None
    max_auto_approve_severity: str | None = None
