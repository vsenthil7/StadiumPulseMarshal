"""W3C Trace Context (traceparent) propagation.

Parses an inbound ``traceparent`` header (version-traceid-spanid-flags); if
present and valid, continues that trace by generating a fresh child span id; if
absent or malformed, starts a new trace. The active trace id is exposed via a
context var and echoed on the response so the whole system shares a trace.

Reference format: ``00-<32 hex trace id>-<16 hex span id>-<2 hex flags>``.
"""
from __future__ import annotations

import re
import secrets
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TRACEPARENT_HEADER = "traceparent"
_TRACEPARENT_RE = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_span_id: ContextVar[str] = ContextVar("span_id", default="")


def get_trace_id() -> str:
    return _trace_id.get()


def get_span_id() -> str:
    return _span_id.get()


def _new_trace_id() -> str:
    return secrets.token_hex(16)  # 32 hex chars


def _new_span_id() -> str:
    return secrets.token_hex(8)  # 16 hex chars


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    """Return (trace_id, parent_span_id) if the header is valid, else None."""
    if not value:
        return None
    m = _TRACEPARENT_RE.match(value.strip().lower())
    if not m:
        return None
    _version, trace_id, parent_span, _flags = m.groups()
    if trace_id == "0" * 32 or parent_span == "0" * 16:
        return None
    return trace_id, parent_span


def format_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


class TraceContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        parsed = parse_traceparent(request.headers.get(TRACEPARENT_HEADER))
        if parsed is not None:
            trace_id, _parent = parsed
        else:
            trace_id = _new_trace_id()
        span_id = _new_span_id()
        _trace_id.set(trace_id)
        _span_id.set(span_id)
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        response = await call_next(request)
        response.headers[TRACEPARENT_HEADER] = format_traceparent(trace_id, span_id)
        return response
