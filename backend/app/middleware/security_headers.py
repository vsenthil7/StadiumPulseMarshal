"""Security response headers.

Adds a baseline set of hardening headers to every response:
- ``Content-Security-Policy`` — restricts script/style/connect origins (the SPA
  is same-origin; tightened defaults with an opt-out for embedding tools);
- ``X-Frame-Options: DENY`` / CSP ``frame-ancestors 'none'`` — clickjacking;
- ``X-Content-Type-Options: nosniff`` — MIME sniffing;
- ``Referrer-Policy: strict-origin-when-cross-origin``;
- ``Strict-Transport-Security`` — only when ``hsts_enabled`` (behind TLS).

All values are config-driven so a deployment can tune the CSP or disable HSTS in
non-TLS environments.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Conservative default CSP for a same-origin SPA. 'unsafe-inline' is permitted
# for styles only (Vite injects a small style block); scripts are same-origin.
_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, csp: str | None = None, hsts: bool = False) -> None:
        super().__init__(app)
        self._csp = csp or _DEFAULT_CSP
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("Content-Security-Policy", self._csp)
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        h.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=()",
        )
        if self._hsts:
            h.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
