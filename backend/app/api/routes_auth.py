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

import secrets
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.auth import get_principal, optional_principal as _optional_principal_dep
from app.core.errors import UnauthorizedError
from app.rbac.policy import Principal

try:  # PyJWT is optional at runtime
    import jwt as _jwt
except Exception:  # pragma: no cover
    _jwt = None  # type: ignore

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DEMO_PASSWORD = "MatchdayDemo123!"

# Mirror of the frontend demo matrix (lib/demo-users.ts): role × 2 venues.
# ``all_venues`` marks cross-venue (platform/estate) principals.
DEMO_USERS: dict[str, dict] = {
    "viewer@arena-north.demo": {"role": "viewer", "venue_id": "venue_arena_north", "name": "Viewer (demo)"},
    "operator@arena-north.demo": {"role": "operator", "venue_id": "venue_arena_north", "name": "Operator (demo)"},
    "responder@arena-north.demo": {"role": "responder", "venue_id": "venue_arena_north", "name": "Responder (demo)"},
    "admin@arena-north.demo": {"role": "admin", "venue_id": "venue_arena_north", "name": "Admin (demo)", "all_venues": True},
    "viewer@olympic-park.demo": {"role": "viewer", "venue_id": "venue_olympic_park", "name": "Viewer (demo)"},
    "operator@olympic-park.demo": {"role": "operator", "venue_id": "venue_olympic_park", "name": "Operator (demo)"},
    "responder@olympic-park.demo": {"role": "responder", "venue_id": "venue_olympic_park", "name": "Responder (demo)"},
    "admin@olympic-park.demo": {"role": "admin", "venue_id": "venue_olympic_park", "name": "Admin (demo)", "all_venues": True},
    "sre@stadiumpulse.demo": {"role": "admin", "venue_id": "venue_arena_north", "name": "Platform SRE (demo)", "all_venues": True},
}

# Fallback secret so the demo login works out-of-the-box when JWT_SECRET is
# unset. If a real secret is configured we use it (so tokens verify under the
# same key the auth dependency uses).
_DEMO_SECRET = "stadiumpulse-demo-secret-not-for-production"


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str | None = None


class LogoutIn(BaseModel):
    refresh_token: str | None = None


def _mint_access_for_subject(request: Request, subject: str) -> str | None:
    """Mint an access JWT for a known subject (demo directory aware)."""
    if _jwt is None:
        return None
    settings = request.app.state.ctx.settings
    now = int(time.time())
    jti = secrets.token_urlsafe(8)
    user = DEMO_USERS.get(subject)
    if user is not None:
        payload = {
            "sub": subject,
            settings.jwt_roles_claim: [user["role"]],
            "venue_id": user["venue_id"],
            "all_venues": bool(user.get("all_venues")),
            "name": user["name"],
            "iat": now,
            "exp": now + 8 * 3600,
            "jti": jti,
        }
    else:
        payload = {"sub": subject, "iat": now, "exp": now + 8 * 3600, "jti": jti}
    return _jwt.encode(payload, _secret(request), algorithm="HS256")


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
    all_venues = bool(user.get("all_venues"))
    payload = {
        "sub": body.email.lower(),
        claim: [user["role"]],
        "venue_id": user["venue_id"],
        "all_venues": all_venues,
        "name": user["name"],
        "iat": now,
        "exp": now + 8 * 3600,
    }
    token = None
    if _jwt is not None:
        token = _jwt.encode(payload, _secret(request), algorithm="HS256")

    # Start a refresh-token family for silent renewal with rotation.
    refresh_token, _family = await request.app.state.ctx.refresh_tokens.issue(
        body.email.lower()
    )

    return {
        "token": token,
        "refresh_token": refresh_token,
        "user": _user_view(body.email.lower(), user),
    }


def _user_view(email: str, user: dict) -> dict:
    return {
        "subject": email,
        "email": email,
        "full_name": user["name"],
        "role": user["role"],
        "venue_id": user["venue_id"],
        "all_venues": bool(user.get("all_venues")),
    }


@router.get("/me")
async def me(
    principal: Principal = Depends(get_principal),
) -> dict:
    """Rehydrate the current session from the presented token.

    Lets the SPA restore identity on refresh without re-prompting. Resolves the
    same Principal the rest of the API uses; 401 if the token is absent/invalid
    (when auth is enabled).
    """
    # Map subject back to the demo directory when possible for a friendly view.
    user = DEMO_USERS.get(principal.subject)
    if user is not None:
        return {"user": _user_view(principal.subject, user)}
    return {
        "user": {
            "subject": principal.subject,
            "email": principal.subject,
            "full_name": principal.subject,
            "role": principal.roles[0].value if principal.roles else "viewer",
            "venue_id": principal.venues[0] if principal.venues else None,
            "all_venues": principal.all_venues,
        }
    }


@router.post("/refresh")
async def refresh(
    request: Request,
    body: RefreshIn = RefreshIn(),
    principal: "Principal | None" = Depends(_optional_principal_dep),
) -> dict:
    """Renew a session, preferring refresh-token rotation.

    If a ``refresh_token`` is supplied it is rotated: the presented token is
    consumed and a new one is issued in the same family. Presenting an
    already-rotated token is treated as theft — the whole family is revoked and
    the call is rejected (401). A fresh access token is returned alongside the
    rotated refresh token.

    With no ``refresh_token`` it falls back to re-minting from a still-valid
    bearer access token (used when refresh tokens aren't tracked).
    """
    from app.services.refresh_store import ReuseError

    store = request.app.state.ctx.refresh_tokens

    if body.refresh_token:
        subject = await store.subject_for(body.refresh_token)
        try:
            rotated = await store.rotate(body.refresh_token)
        except ReuseError as exc:
            raise UnauthorizedError(
                "Refresh token reuse detected; session revoked"
            ) from exc
        if rotated is None or subject is None:
            raise UnauthorizedError("Invalid or expired refresh token")
        new_refresh, _fam = rotated
        access = _mint_access_for_subject(request, subject)
        return {
            "token": access,
            "refresh_token": new_refresh,
            "expires_in": 8 * 3600,
        }

    # Fallback: bearer re-mint (requires a valid access token).
    if principal is None:
        raise UnauthorizedError("Authentication required")
    access = _mint_access_for_subject(request, principal.subject)
    if access is None:
        return {"token": None}
    return {"token": access, "expires_in": 8 * 3600}


@router.post("/logout")
async def logout(request: Request, body: LogoutIn = LogoutIn()) -> dict:
    """Revoke the active refresh-token family so it cannot be rotated again."""
    if body.refresh_token:
        await request.app.state.ctx.refresh_tokens.revoke_token(body.refresh_token)
    return {"ok": True}


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


# ── OIDC SSO (optional) ──────────────────────────────────────────────────────
from fastapi.responses import RedirectResponse  # noqa: E402

from app.services.oidc_service import OIDCError, OIDCService  # noqa: E402

oidc_router = APIRouter(prefix="/api/v1/auth/oidc", tags=["auth"])


def _oidc(request: Request) -> OIDCService:
    # Cache one service on app state.
    svc = getattr(request.app.state, "_oidc", None)
    if svc is None:
        svc = OIDCService(request.app.state.ctx.settings)
        request.app.state._oidc = svc
    return svc


@oidc_router.get("/status")
async def oidc_status(request: Request) -> dict:
    """Whether SSO is available — lets the SPA show/hide the SSO button."""
    return {"enabled": _oidc(request).enabled}


@oidc_router.get("/login")
async def oidc_login(request: Request, return_to: str = "/"):
    svc = _oidc(request)
    if not svc.enabled:
        raise UnauthorizedError("OIDC is not configured")
    try:
        url = await svc.authorization_url(return_to)
    except OIDCError as exc:
        raise UnauthorizedError(str(exc)) from exc
    return RedirectResponse(url, status_code=307)


@oidc_router.get("/callback")
async def oidc_callback(request: Request, code: str | None = None, state: str | None = None):
    svc = _oidc(request)
    if not svc.enabled:
        raise UnauthorizedError("OIDC is not configured")
    if not code or not state:
        raise UnauthorizedError("Missing code/state")
    data = svc.verify_state(state)
    try:
        identity = await svc.exchange_code(code, expected_nonce=data.get("n", ""))
    except OIDCError as exc:
        raise UnauthorizedError(str(exc)) from exc
    token = svc.mint_session_jwt(identity)
    # Hand the SPA its session token via the redirect fragment (not query, so it
    # never lands in server logs), then the SPA stores it like any login.
    return_to = data.get("r", "/")
    return RedirectResponse(f"{return_to}#oidc_token={token}", status_code=307)
