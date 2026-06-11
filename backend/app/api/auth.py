"""Authentication dependencies.

When ``auth_enabled`` is set, endpoints require either a matching ``X-API-Key``
header or a valid Bearer JWT signed with ``jwt_secret``. When disabled (default
for the demo), all requests pass. Kept as a FastAPI dependency so it composes.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, Request

try:  # PyJWT is optional at runtime
    import jwt as _jwt
except Exception:  # pragma: no cover - jwt always present in this env
    _jwt = None  # type: ignore


def _decode_jwt(token: str, secret: str) -> dict:
    if _jwt is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="JWT support unavailable")
    try:
        return _jwt.decode(token, secret, algorithms=["HS256"])
    except Exception as exc:  # pragma: no cover - exercised via wrong token test
        raise HTTPException(status_code=401, detail="Invalid token") from exc


async def require_auth(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    """Authorise a request. Returns a principal dict (or {} when auth is off)."""
    settings = request.app.state.ctx.settings
    if not settings.auth_enabled:
        return {"principal": "anonymous", "auth": "disabled"}

    # API key path.
    if settings.api_key and x_api_key == settings.api_key:
        return {"principal": "api-key", "auth": "api_key"}

    # JWT path.
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        if settings.jwt_secret:
            claims = _decode_jwt(token, settings.jwt_secret)
            return {"principal": claims.get("sub", "jwt-user"), "auth": "jwt"}

    raise HTTPException(status_code=401, detail="Authentication required")
