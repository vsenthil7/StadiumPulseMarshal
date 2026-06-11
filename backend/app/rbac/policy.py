"""Role-based access control: roles, permissions and their mapping.

Permissions are fine-grained strings (e.g. ``incident:write``). Roles bundle
permissions. A principal carries roles; a route declares a required permission.
The auth layer resolves an API key or JWT to a principal with roles.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Permission(str, Enum):
    INCIDENT_READ = "incident:read"
    INCIDENT_WRITE = "incident:write"
    REMEDIATION_READ = "remediation:read"
    REMEDIATION_APPROVE = "remediation:approve"
    SLO_READ = "slo:read"
    ANALYTICS_READ = "analytics:read"
    SCENARIO_WRITE = "scenario:write"
    WEBHOOK_ADMIN = "webhook:admin"
    SETTINGS_WRITE = "settings:write"


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    RESPONDER = "responder"
    ADMIN = "admin"


# Role → permissions matrix.
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {
        Permission.INCIDENT_READ,
        Permission.REMEDIATION_READ,
        Permission.SLO_READ,
        Permission.ANALYTICS_READ,
    },
    Role.OPERATOR: {
        Permission.INCIDENT_READ,
        Permission.INCIDENT_WRITE,
        Permission.REMEDIATION_READ,
        Permission.SLO_READ,
        Permission.ANALYTICS_READ,
        Permission.SCENARIO_WRITE,
    },
    Role.RESPONDER: {
        Permission.INCIDENT_READ,
        Permission.INCIDENT_WRITE,
        Permission.REMEDIATION_READ,
        Permission.REMEDIATION_APPROVE,
        Permission.SLO_READ,
        Permission.ANALYTICS_READ,
        Permission.SCENARIO_WRITE,
    },
    Role.ADMIN: set(Permission),  # all permissions
}


class Principal(BaseModel):
    """An authenticated identity with roles."""

    subject: str
    roles: list[Role] = Field(default_factory=list)
    auth_method: str = "none"

    @property
    def permissions(self) -> set[Permission]:
        perms: set[Permission] = set()
        for role in self.roles:
            perms |= ROLE_PERMISSIONS.get(role, set())
        return perms

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions


def roles_from_names(names: list[str]) -> list[Role]:
    """Map arbitrary role name strings to known Roles (unknown ignored)."""
    out: list[Role] = []
    for n in names:
        try:
            out.append(Role(n))
        except ValueError:
            continue
    return out


# When auth is disabled, requests act as a full-access admin so the demo works.
ANONYMOUS_ADMIN = Principal(
    subject="anonymous", roles=[Role.ADMIN], auth_method="disabled"
)
