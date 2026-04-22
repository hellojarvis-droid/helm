"""HTTP middleware.

CorrelationIdMiddleware stamps every request with a trace_id, propagates
it through structlog contextvars, echoes it back on the response. Same
trace_id surfaces into Sentry + Langfuse — one ID across every layer.

It also emits a structured request log line per request (skipping the
chatty liveness probe so logs don't drown in /health spam) so ops can
slice latency + status by route / user / trace_id without parsing raw
access logs.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TRACE_HEADER = "x-trace-id"

log = structlog.get_logger("helm.http")

# Probes hit /health every few seconds — logging them drowns the signal.
# /ready is louder per call but fires on a slower cadence; keep it logged.
_QUIET_PATHS = frozenset({"/health"})


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or uuid.uuid4().hex
        request.state.trace_id = trace_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
        )
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if request.url.path not in _QUIET_PATHS:
                log.warning("request.failed", duration_ms=elapsed_ms)
            raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if request.url.path not in _QUIET_PATHS:
            log.info(
                "request.completed",
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
        response.headers[TRACE_HEADER] = trace_id
        return response
