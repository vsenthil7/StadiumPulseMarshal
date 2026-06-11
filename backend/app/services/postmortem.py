"""Postmortem generation from an incident's timeline.

Produces a structured postmortem (summary, timeline, metrics, contributing
remediations) suitable for export. Pure function over an Incident.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.incident import Incident, IncidentEventType


class PostmortemTimelineItem(BaseModel):
    at: str
    actor: str
    event: str
    detail: str


class Postmortem(BaseModel):
    incident_id: str
    title: str
    severity: str
    final_state: str
    summary: str
    tta_minutes: float | None = None
    ttr_minutes: float | None = None
    escalation_tier: str = ""
    remediation_ids: list[str] = Field(default_factory=list)
    timeline: list[PostmortemTimelineItem] = Field(default_factory=list)
    markdown: str = ""


def _summarise(incident: Incident) -> str:
    parts = [
        f"Incident {incident.id} ({incident.severity.value}) — "
        f"{incident.title}.",
    ]
    if incident.impact_summary:
        parts.append(f"Impact: {incident.impact_summary}")
    if incident.ttr_minutes is not None:
        parts.append(f"Resolved in {incident.ttr_minutes:.1f} min.")
    escalations = [
        e for e in incident.timeline
        if e.type == IncidentEventType.ESCALATED
    ]
    if escalations:
        parts.append(f"Escalated {len(escalations)} time(s).")
    return " ".join(parts)


def generate_postmortem(incident: Incident) -> Postmortem:
    timeline = [
        PostmortemTimelineItem(
            at=ev.at.isoformat(), actor=ev.actor, event=ev.type.value,
            detail=ev.detail,
        )
        for ev in incident.timeline
    ]
    summary = _summarise(incident)

    md_lines = [
        f"# Postmortem — {incident.title}",
        "",
        f"- **Incident**: {incident.id}",
        f"- **Severity**: {incident.severity.value}",
        f"- **Final state**: {incident.state.value}",
        f"- **Escalation tier**: {incident.tier.value}",
    ]
    if incident.tta_minutes is not None:
        md_lines.append(f"- **Time to acknowledge**: {incident.tta_minutes:.1f} min")
    if incident.ttr_minutes is not None:
        md_lines.append(f"- **Time to resolve**: {incident.ttr_minutes:.1f} min")
    md_lines += ["", "## Summary", "", summary, "", "## Timeline", ""]
    for item in timeline:
        md_lines.append(f"- `{item.at}` **{item.event}** ({item.actor}): {item.detail}")
    if incident.remediation_ids:
        md_lines += ["", "## Remediations applied", ""]
        md_lines += [f"- {rid}" for rid in incident.remediation_ids]

    return Postmortem(
        incident_id=incident.id,
        title=incident.title,
        severity=incident.severity.value,
        final_state=incident.state.value,
        summary=summary,
        tta_minutes=incident.tta_minutes,
        ttr_minutes=incident.ttr_minutes,
        escalation_tier=incident.tier.value,
        remediation_ids=list(incident.remediation_ids),
        timeline=timeline,
        markdown="\n".join(md_lines),
    )
