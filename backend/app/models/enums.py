"""Domain enumerations shared across models."""
from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    """Problem severity, ordered low→critical."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        order = {
            "INFO": 0,
            "LOW": 1,
            "MEDIUM": 2,
            "HIGH": 3,
            "CRITICAL": 4,
        }
        return order[self.value]

    def __lt__(self, other: "Severity") -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank < other.rank


class ProblemStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class EntityType(str, Enum):
    SERVICE = "SERVICE"
    APPLICATION = "APPLICATION"
    HOST = "HOST"
    PROCESS = "PROCESS"
    DATABASE = "DATABASE"
    NETWORK = "NETWORK"
    KUBERNETES = "KUBERNETES"


class MatchdayPhase(str, Enum):
    """Where in the matchday timeline we are — drives surge expectations."""

    PRE_GATES = "PRE_GATES"          # before gates open
    GATES_OPEN = "GATES_OPEN"        # entry surge: scanning, payments
    KICKOFF = "KICKOFF"              # app/stream surge
    HALFTIME = "HALFTIME"            # concessions/payment surge
    SECOND_HALF = "SECOND_HALF"
    FULL_TIME = "FULL_TIME"          # egress, transport
    POST_MATCH = "POST_MATCH"


class RemediationStatus(str, Enum):
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    AUTO_APPROVED = "AUTO_APPROVED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def rank(self) -> int:
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}[self.value]
