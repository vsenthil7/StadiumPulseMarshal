"""Request metrics and timing-log middleware."""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.middleware.correlation import get_request_id
from app.observability.metrics import get_metrics

log = get_logger("request")


def _route_template(request: Request) -> str:
    """Use the matched route path template to keep label cardinality low."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = _route_template(request)
        get_metrics().observe_request(
            request.method, path, response.status_code, duration
        )
        log.info(
            "%s %s -> %s %.1fms [%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration * 1000,
            get_request_id(),
        )
        return response
