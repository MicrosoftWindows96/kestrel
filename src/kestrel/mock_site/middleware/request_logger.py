"""Request logger middleware (Phase A scope).

Per plan section 11.1: outermost middleware. Wraps each request in
`structlog.contextvars.bound_contextvars(request_id=uuid.uuid4().hex)`
and emits a `request` event on every non-skipped path, including the
exception path (status 500). Section 11 extends this to the final form
(per-step bind, shutdown histogram, all extra fields). Health and
static paths are skipped so probes do not pollute logs.
"""

from __future__ import annotations

import time
import uuid
from typing import Final

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

ERROR_STATUS: Final[int] = 500

SKIP_EXACT: Final[frozenset[str]] = frozenset({"/healthz", "/readyz", "/static"})
SKIP_PREFIXES: Final[tuple[str, ...]] = ("/static/",)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if _should_skip(path):
            return await call_next(request)

        request_id = uuid.uuid4().hex
        settings = request.app.state.settings
        start = time.perf_counter()
        status = ERROR_STATUS
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                response = await call_next(request)
                status = response.status_code
                return response
            finally:
                duration_ms = round((time.perf_counter() - start) * 1000.0, 3)
                structlog.get_logger("kestrel.mock_site.request").info(
                    "request",
                    method=request.method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    difficulty=settings.difficulty.value,
                    persona=settings.persona.value,
                )


def _should_skip(path: str) -> bool:
    if path in SKIP_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in SKIP_PREFIXES)
