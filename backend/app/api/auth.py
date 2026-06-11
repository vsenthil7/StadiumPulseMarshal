"""Authentication + authorization dependencies.

Resolves a request to an RBAC ``Principal`` (API key or JWT), and provides a
``require_permission`` factory for route-level authorization. When auth is
disabled the request acts as a full-access admin so the demo runs unguarded.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, Request

from app.core.errors import ForbiddenError, UnauthorizedError
from app.rbac.policy import (
    ANONYMOUS_ADMIN,
    Permission,
    Principal,
    roles_from_names,
)

try:  # PyJWT is optional at runtime
    import jwt as _jwt
except Exception:  # pragma: no cover
    _jwt = None  # type: ignore


def _decode_jwt(token: str, secret: str) -> dict:
    if _jwt is None:  # pragma: no cover
        raise UnauthorizedError("JWT support unavailable")
    try:
        return _jwt.decode(token, secret, algorithms=["HS256"])
    except Exception as exc:
        raise UnauthorizedError("Invalid token") from exc


def _claim_roles(claims: dict, claim_name: str) -> list[str]:
    raw = claims.get(claim_name, [])
    if isinstance(raw, str):
        return [r.strip() for r in raw.split(",") if r.strip()]
    if isinstance(raw, list):
        return [str(r) for r in raw]
    return []


async def get_principal(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    """Resolve the current principal (or raise 401)."""
    settings = request.app.state.ctx.settings
    if not settings.auth_enabled:
        return ANONYMOUS_ADMIN

    if settings.api_key and x_api_key == settings.api_key:
        return Principal(
            subject="api-key",
            roles=roles_from_names(settings.api_key_role_list),
            auth_method="api_key",
        )

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        if settings.jwt_secret:
            claims = _decode_jwt(token, settings.jwt_secret)
            roles = _claim_roles(claims, settings.jwt_roles_claim)
            return Principal(
                subject=str(claims.get("sub", "jwt-user")),
                roles=roles_from_names(roles),
                auth_method="jwt",
            )

    raise UnauthorizedError("Authentication required")


def require_permission(permission: Permission) -> Callable:
    """Dependency factory enforcing a permission on the resolved principal."""

    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise ForbiddenError(
                f"Missing permission: {permission.value}",
                details={"required": permission.value},
            )
        return principal

    return _dep


# Backwards-compatible alias: authentication only (no specific permission).
async def require_auth(principal: Principal = Depends(get_principal)) -> Principal:
    return principal
