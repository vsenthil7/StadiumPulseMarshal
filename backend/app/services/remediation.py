"""Remediation planning.

Maps a problem's root cause to concrete, ranked remediation actions with
runbooks, risk and estimated MTTR. This is deterministic and used by both the
mock agent and as a grounding tool for the live Gemini agent.
"""
from __future__ import annotations

import uuid

from app.models.domain import Problem, RemediationAction
from app.models.enums import EntityType, RiskLevel


def _new_id() -> str:
    return f"RA-{uuid.uuid4().hex[:8]}"


def plan_remediations(problem: Problem) -> list[RemediationAction]:
    """Produce ranked remediation actions for a problem."""
    actions: list[RemediationAction] = []
    rc = problem.root_cause
    root_entity_type: EntityType | None = None

    # Descend to the deepest flagged root cause.
    node = rc
    while node is not None:
        if node.is_root_cause:
            root_entity_type = node.entity_type
            break
        node = node.children[0] if node.children else None

    if root_entity_type == EntityType.DATABASE:
        actions.append(
            RemediationAction(
                id=_new_id(),
                problem_id=problem.id,
                title="Increase database connection pool ceiling",
                description=(
                    "Raise max_connections and the service-side pool size to "
                    "absorb the matchday surge, then recycle saturated "
                    "connections."
                ),
                runbook=[
                    "Confirm pool saturation in Dynatrace metric "
                    "db.connections.active == max.",
                    "Apply temporary max_connections increase (e.g. 100 → 200).",
                    "Scale service connection pool to match.",
                    "Verify p95 latency recovers below 300ms.",
                ],
                risk=RiskLevel.MEDIUM,
                estimated_mttr_minutes=6.0,
                requires_approval=True,
            )
        )
        actions.append(
            RemediationAction(
                id=_new_id(),
                problem_id=problem.id,
                title="Enable read-replica offload",
                description=(
                    "Route read-only payment status checks to a replica to "
                    "relieve the primary."
                ),
                runbook=[
                    "Confirm replica lag < 1s.",
                    "Flip read traffic to replica via feature flag.",
                    "Monitor primary connection count.",
                ],
                risk=RiskLevel.LOW,
                estimated_mttr_minutes=4.0,
                requires_approval=True,
            )
        )
    elif root_entity_type in (EntityType.SERVICE, EntityType.APPLICATION):
        actions.append(
            RemediationAction(
                id=_new_id(),
                problem_id=problem.id,
                title="Horizontal scale-out of affected service",
                description="Add replicas to absorb surge load.",
                runbook=[
                    "Increase replica count by 50%.",
                    "Confirm load balancer health checks pass.",
                    "Verify latency normalises.",
                ],
                risk=RiskLevel.LOW,
                estimated_mttr_minutes=5.0,
                requires_approval=True,
            )
        )
    else:
        actions.append(
            RemediationAction(
                id=_new_id(),
                problem_id=problem.id,
                title="Escalate to on-call SRE for manual triage",
                description=(
                    "Root cause not auto-classified; route to human with full "
                    "context pack."
                ),
                runbook=[
                    "Attach Dynatrace problem link and timeline.",
                    "Page on-call SRE.",
                ],
                risk=RiskLevel.LOW,
                estimated_mttr_minutes=10.0,
                requires_approval=True,
            )
        )

    return actions
