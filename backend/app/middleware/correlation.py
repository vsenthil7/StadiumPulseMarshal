"""Correlation-ID propagation.

A per-request id is generated (or taken from an inbound ``X-Request-ID``),
stored in a context variable so any code can read it (e.g. for logging), and
echoed on the response. This gives every request and every log line / error a
traceable id.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a correlation id for each request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        set_request_id(rid)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
