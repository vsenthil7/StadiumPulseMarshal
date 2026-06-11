"""Exception handlers that emit the standard error envelope.

Registered on the FastAPI app. Converts AppError subclasses, FastAPI
HTTPException and any unhandled exception into the uniform envelope, attaching
the current correlation id.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.core.errors import AppError, RateLimitedError, error_envelope
from app.core.logging import get_logger
from app.middleware.correlation import get_request_id
from app.middleware.tracing import get_trace_id

log = get_logger(__name__)

# Map common HTTP status codes to stable error codes.
_STATUS_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        rid = get_request_id()
        headers = {}
        if isinstance(exc, RateLimitedError):
            headers["Retry-After"] = str(exc.retry_after)
        log.warning("AppError %s: %s [%s]", exc.code, exc.message, rid)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.code, exc.message, rid, exc.details, get_trace_id()),
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def _http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        rid = get_request_id()
        code = _STATUS_CODE.get(exc.status_code, "error")
        detail = exc.detail if isinstance(exc.detail, str) else "error"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code, detail, rid, trace_id=get_trace_id()),
            headers=getattr(exc, "headers", None) or {},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = get_request_id()
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "validation_error", "Request validation failed", rid,
                {"errors": exc.errors()}, get_trace_id(),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        rid = get_request_id()
        log.exception("Unhandled error [%s]: %s", rid, exc)
        return JSONResponse(
            status_code=500,
            content=error_envelope("internal_error", "Internal server error", rid, trace_id=get_trace_id()),
        )
