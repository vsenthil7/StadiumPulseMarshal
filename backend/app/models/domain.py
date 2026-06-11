"""Pydantic domain models for StadiumPulse Marshal.

These model the slice of Dynatrace observability data the agent reasons over,
plus the matchday-specific and human-in-the-loop remediation constructs.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .enums import (
    EntityType,
    MatchdayPhase,
    ProblemStatus,
    RemediationStatus,
    RiskLevel,
    Severity,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Entity(BaseModel):
    """A monitored entity (service, host, app...)."""

    id: str
    name: str
    type: EntityType
    tags: list[str] = Field(default_factory=list)
    health: float = Field(default=100.0, ge=0.0, le=100.0)


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float


class Metric(BaseModel):
    key: str
    unit: str
    entity_id: str
    points: list[MetricPoint] = Field(default_factory=list)

    @property
    def latest(self) -> float | None:
        return self.points[-1].value if self.points else None


class Event(BaseModel):
    id: str
    title: str
    entity_id: str
    timestamp: datetime
    description: str = ""


class RootCauseNode(BaseModel):
    """A node in the Davis-AI-style causal tree."""

    entity_id: str
    entity_name: str
    entity_type: EntityType
    is_root_cause: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    contribution: str = ""
    children: list["RootCauseNode"] = Field(default_factory=list)


class FixtureTimelineEntry(BaseModel):
    """A point on the match timeline used to correlate load with incidents."""

    phase: MatchdayPhase
    label: str
    starts_at: datetime
    expected_load_multiplier: float = Field(default=1.0, ge=0.0)


class Problem(BaseModel):
    """A Dynatrace problem the agent triages."""

    id: str
    title: str
    severity: Severity
    status: ProblemStatus
    opened_at: datetime = Field(default_factory=_utcnow)
    resolved_at: datetime | None = None
    affected_entities: list[Entity] = Field(default_factory=list)
    root_cause: RootCauseNode | None = None
    events: list[Event] = Field(default_factory=list)
    matchday_phase: MatchdayPhase | None = None
    impact_summary: str = ""

    @property
    def is_open(self) -> bool:
        return self.status == ProblemStatus.OPEN


class RemediationAction(BaseModel):
    """A remediation the agent proposes for a problem."""

    id: str
    problem_id: str
    title: str
    description: str
    runbook: list[str] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.MEDIUM
    status: RemediationStatus = RemediationStatus.PROPOSED
    estimated_mttr_minutes: float = 0.0
    requires_approval: bool = True
    created_at: datetime = Field(default_factory=_utcnow)


class ApprovalDecision(BaseModel):
    """Audit record of a human (or auto) approval decision."""

    remediation_id: str
    approved: bool
    decided_by: str
    reason: str = ""
    decided_at: datetime = Field(default_factory=_utcnow)
    auto: bool = False


class AgentAnalysis(BaseModel):
    """The agent's reasoning output for a problem."""

    problem_id: str
    summary: str
    root_cause: RootCauseNode | None = None
    correlated_phase: MatchdayPhase | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recommended_actions: list[RemediationAction] = Field(default_factory=list)
    reasoning: str = ""
    generated_by: str = "mock"


RootCauseNode.model_rebuild()
