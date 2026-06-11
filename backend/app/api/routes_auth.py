"""Demo authentication endpoint.

Mints a short-lived JWT for the demo identity matrix so the console's LIVE login
path works end-to-end without an external IdP. The token carries the role claim
the existing ``get_principal`` dependency already understands, so the very same
RBAC enforcement applies whether auth is enabled or not.

This is a *demo* affordance (a fixed shared password, an in-code user list). In
production these endpoints would be replaced by a real IdP / OIDC flow; the
token shape and role claim stay the same.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.errors import UnauthorizedError

try:  # PyJWT is optional at runtime
    import jwt as _jwt
except Exception:  # pragma: no cover
    _jwt = None  # type: ignore

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DEMO_PASSWORD = "MatchdayDemo123!"

# Mirror of the frontend demo matrix (lib/demo-users.ts): role × 2 venues.
DEMO_USERS: dict[str, dict] = {
    "viewer@arena-north.demo": {"role": "viewer", "venue_id": "venue_arena_north", "name": "Viewer (demo)"},
    "operator@arena-north.demo": {"role": "operator", "venue_id": "venue_arena_north", "name": "Operator (demo)"},
    "responder@arena-north.demo": {"role": "responder", "venue_id": "venue_arena_north", "name": "Responder (demo)"},
    "admin@arena-north.demo": {"role": "admin", "venue_id": "venue_arena_north", "name": "Admin (demo)"},
    "viewer@olympic-park.demo": {"role": "viewer", "venue_id": "venue_olympic_park", "name": "Viewer (demo)"},
    "operator@olympic-park.demo": {"role": "operator", "venue_id": "venue_olympic_park", "name": "Operator (demo)"},
    "responder@olympic-park.demo": {"role": "responder", "venue_id": "venue_olympic_park", "name": "Responder (demo)"},
    "admin@olympic-park.demo": {"role": "admin", "venue_id": "venue_olympic_park", "name": "Admin (demo)"},
    "sre@stadiumpulse.demo": {"role": "admin", "venue_id": "venue_arena_north", "name": "Platform SRE (demo)"},
}

# Fallback secret so the demo login works out-of-the-box when JWT_SECRET is
# unset. If a real secret is configured we use it (so tokens verify under the
# same key the auth dependency uses).
_DEMO_SECRET = "stadiumpulse-demo-secret-not-for-production"


class LoginIn(BaseModel):
    email: str
    password: str


def _secret(request: Request) -> str:
    configured = request.app.state.ctx.settings.jwt_secret
    return configured or _DEMO_SECRET


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    user = DEMO_USERS.get(body.email.lower())
    if user is None or body.password != DEMO_PASSWORD:
        raise UnauthorizedError("Invalid email or password")

    settings = request.app.state.ctx.settings
    claim = settings.jwt_roles_claim
    now = int(time.time())
    payload = {
        "sub": body.email.lower(),
        claim: [user["role"]],
        "venue_id": user["venue_id"],
        "name": user["name"],
        "iat": now,
        "exp": now + 8 * 3600,
    }
    token = None
    if _jwt is not None:
        token = _jwt.encode(payload, _secret(request), algorithm="HS256")

    return {
        "token": token,
        "user": {
            "subject": body.email.lower(),
            "email": body.email.lower(),
            "full_name": user["name"],
            "role": user["role"],
            "venue_id": user["venue_id"],
        },
    }


@router.get("/demo-users")
async def demo_users() -> dict:
    """List demo accounts (without secrets) for the login quick-fill."""
    return {
        "password": DEMO_PASSWORD,
        "users": [
            {"email": e, "role": u["role"], "venue_id": u["venue_id"]}
            for e, u in DEMO_USERS.items()
        ],
    }
