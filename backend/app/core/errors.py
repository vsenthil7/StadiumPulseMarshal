"""Standard error envelope and application exception types.

Every error response shares one shape:

    {"error": {"code": str, "message": str, "request_id": str, "details": {...}}}

so clients can handle failures uniformly. Domain code raises ``AppError``
subclasses; the exception handlers (registered in ``middleware.errors``) convert
them — and any unhandled exception — into this envelope.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base application error with an HTTP status and a stable error code."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self, message: str, *, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(
        self, message: str, *, retry_after: int = 1,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after = retry_after


def error_envelope(
    code: str, message: str, request_id: str, details: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    env: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or {},
        }
    }
    if trace_id:
        env["error"]["trace_id"] = trace_id
    return env
