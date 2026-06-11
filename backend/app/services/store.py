"""Remediation store: tracks proposed actions, approvals and an audit log.

In a production deployment this would be backed by a database; for the
hackathon build it is an in-memory store with the same async interface, so it
can be swapped without touching callers.
"""
from __future__ import annotations

from app.core.config import Settings
from app.models.domain import ApprovalDecision, RemediationAction
from app.models.enums import RemediationStatus, RiskLevel, Severity


class RemediationStore:
    """Holds remediation actions and decisions for the session."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._actions: dict[str, RemediationAction] = {}
        self._audit: list[ApprovalDecision] = []

    # --- registration ------------------------------------------------------
    def register(self, actions: list[RemediationAction]) -> None:
        for a in actions:
            self._actions.setdefault(a.id, a)

    def get(self, action_id: str) -> RemediationAction | None:
        return self._actions.get(action_id)

    def list_actions(self) -> list[RemediationAction]:
        return list(self._actions.values())

    def pending(self) -> list[RemediationAction]:
        return [
            a
            for a in self._actions.values()
            if a.status
            in (RemediationStatus.PROPOSED, RemediationStatus.AWAITING_APPROVAL)
        ]

    def audit_log(self) -> list[ApprovalDecision]:
        return list(self._audit)

    # --- guardrails --------------------------------------------------------
    def can_auto_approve(
        self, action: RemediationAction, problem_severity: Severity
    ) -> bool:
        """Auto-approve only if enabled, low-risk, and within severity ceiling."""
        if not self._settings.auto_approve_low_risk:
            return False
        if action.risk != RiskLevel.LOW:
            return False
        ceiling = Severity(self._settings.max_auto_approve_severity)
        return problem_severity.rank <= ceiling.rank

    # --- decisions ---------------------------------------------------------
    def decide(
        self,
        action_id: str,
        *,
        approved: bool,
        decided_by: str,
        reason: str = "",
        auto: bool = False,
    ) -> ApprovalDecision | None:
        action = self._actions.get(action_id)
        if action is None:
            return None
        if approved:
            action.status = (
                RemediationStatus.AUTO_APPROVED
                if auto
                else RemediationStatus.APPROVED
            )
        else:
            action.status = RemediationStatus.REJECTED
        decision = ApprovalDecision(
            remediation_id=action_id,
            approved=approved,
            decided_by=decided_by,
            reason=reason,
            auto=auto,
        )
        self._audit.append(decision)
        return decision

    def mark_executed(self, action_id: str, *, success: bool) -> bool:
        action = self._actions.get(action_id)
        if action is None:
            return False
        action.status = (
            RemediationStatus.EXECUTED if success else RemediationStatus.FAILED
        )
        return True
