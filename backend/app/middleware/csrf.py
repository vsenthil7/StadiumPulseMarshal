"""CSRF protection (double-submit cookie).

Cross-site request forgery only applies to *credentialed* requests the browser
sends automatically — i.e. cookie-based auth. Token-based auth (Authorization:
Bearer / X-API-Key) is immune because a cross-site page cannot read or set those
headers. So this middleware enforces a double-submit token **only** for unsafe
methods that are NOT already authenticated by a header credential.

Mechanism: the client reads a ``csrf_token`` cookie (set on safe GETs) and
echoes it in an ``X-CSRF-Token`` header on state-changing requests. A request
whose header token doesn't match the cookie is rejected (403). Requests bearing
an ``Authorization``/``X-API-Key`` header are exempt (not cookie-credentialed).
"""
from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import error_envelope
from app.middleware.correlation import get_request_id

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_COOKIE = "csrf_token"
_HEADER = "x-csrf-token"


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, cookie_secure: bool = False) -> None:
        super().__init__(app)
        self._secure = cookie_secure

    def _exempt(self, request: Request) -> bool:
        # Header-credentialed requests are not cookie-CSRF-able.
        if request.headers.get("authorization") or request.headers.get("x-api-key"):
            return True
        return request.method in _SAFE_METHODS

    async def dispatch(self, request: Request, call_next) -> Response:
        enforce = not self._exempt(request)
        if enforce:
            cookie = request.cookies.get(_COOKIE)
            header = request.headers.get(_HEADER)
            if not cookie or not header or not secrets.compare_digest(cookie, header):
                return JSONResponse(
                    status_code=403,
                    content=error_envelope(
                        "csrf_failed",
                        "Missing or invalid CSRF token",
                        get_request_id(),
                        {},
                    ),
                )
        response = await call_next(request)
        # Issue/refresh the CSRF cookie on safe navigations so the SPA can read
        # it for subsequent unsafe requests (double-submit).
        if request.method in _SAFE_METHODS and _COOKIE not in request.cookies:
            token = secrets.token_urlsafe(32)
            response.set_cookie(
                _COOKIE, token,
                httponly=False,  # must be readable by JS to echo in the header
                samesite="strict",
                secure=self._secure,
                path="/",
            )
        return response
