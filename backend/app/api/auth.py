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
    Role,
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


def _venue_scope(claims: dict, roles: list[Role]) -> tuple[list[str], bool]:
    """Derive a principal's venue scope from JWT claims.

    Recognised claims: ``all_venues`` (bool) and ``venues`` (list) or a single
    ``venue_id``. If a token carries no venue information at all, the principal
    is treated as unconstrained (cross-venue) — venue restriction applies only
    when the issuer explicitly scopes the token. This keeps tokens that predate
    venue scoping working while letting scoped tokens be enforced.
    """
    if claims.get("all_venues") is True:
        return [], True
    venues: list[str] = []
    raw = claims.get("venues")
    if isinstance(raw, list):
        venues = [str(v) for v in raw]
    elif isinstance(raw, str) and raw:
        venues = [v.strip() for v in raw.split(",") if v.strip()]
    single = claims.get("venue_id")
    if single and single not in venues:
        venues.append(str(single))
    if not venues:
        # No venue information in the token → unconstrained.
        return [], True
    return venues, False


async def get_principal(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    """Resolve the current principal (or raise 401).

    When auth is disabled the request normally acts as a full-access admin so
    the demo runs unguarded. However, if the caller *does* present a bearer
    token we honor it — this lets the demo console sign in as a specific role
    and see real RBAC gating without flipping a global flag. A demo fallback
    secret is accepted so the bundled login works out-of-the-box.
    """
    settings = request.app.state.ctx.settings

    # API key (only meaningful when configured).
    if settings.api_key and x_api_key == settings.api_key:
        return Principal(
            subject="api-key",
            roles=roles_from_names(settings.api_key_role_list),
            auth_method="api_key",
            all_venues=True,
        )

    # Bearer token: try the configured secret, then the demo fallback secret.
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        from app.api.routes_auth import _DEMO_SECRET

        for secret in filter(None, (settings.jwt_secret, _DEMO_SECRET)):
            try:
                claims = _decode_jwt(token, secret)
            except UnauthorizedError:
                continue
            roles = _claim_roles(claims, settings.jwt_roles_claim)
            resolved = roles_from_names(roles)
            venues, all_venues = _venue_scope(claims, resolved)
            return Principal(
                subject=str(claims.get("sub", "jwt-user")),
                roles=resolved,
                auth_method="jwt",
                venues=venues,
                all_venues=all_venues,
            )
        # A token was presented but did not verify under any known secret.
        raise UnauthorizedError("Invalid token")

    if not settings.auth_enabled:
        return ANONYMOUS_ADMIN

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


def require_venue_access(principal: Principal, venue_id: str | None) -> None:
    """Raise 403 if the principal may not act within ``venue_id``.

    Centralises venue-scope enforcement so routes that accept a ``venue_id``
    (query or body) can authorize it consistently. A ``None`` venue is allowed
    (estate-wide / unscoped resource).
    """
    if not principal.can_access_venue(venue_id):
        raise ForbiddenError(
            "Venue not in principal scope",
            details={"venue_id": venue_id or ""},
        )


def scope_collection(principal: Principal, items: list, venue_filter: str | None = None):
    """Filter a list of venue-bearing items to those the principal may see.

    Items without a ``venue_id`` (estate-wide) are always included. When an
    explicit ``venue_filter`` is supplied it is authorized first, then applied.
    """
    if venue_filter is not None:
        require_venue_access(principal, venue_filter)
        return [
            it for it in items
            if getattr(it, "venue_id", None) in (None, venue_filter)
        ]
    if principal.all_venues:
        return items
    allowed = set(principal.venues)
    return [
        it for it in items
        if getattr(it, "venue_id", None) is None
        or getattr(it, "venue_id", None) in allowed
    ]


# Backwards-compatible alias: authentication only (no specific permission).
async def require_auth(principal: Principal = Depends(get_principal)) -> Principal:
    return principal
