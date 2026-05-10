"""Request logger middleware (final form).

Plan section 11.1 / section 16: outermost middleware in the stack so the
emitted `request` event captures the final status code returned to the
client, the elapsed duration across every inner middleware and the
route handler, and the per-request context (`request_id`, `session_id`)
that downstream events bind onto via `structlog.contextvars`.

The middleware skips `/healthz`, `/readyz`, and `/static/*` so probes
and asset fetches do not pollute the structured log stream. The
`X-Request-Id` request header is intentionally ignored; `request_id`
is always server-generated to defend against client-supplied collisions
and log-stuffing.
"""

from __future__ import annotations

import re
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
SESSION_COOKIE: Final[str] = "kestrel_session"

_QUOTE_STEP_RE: Final[re.Pattern[str]] = re.compile(r"^/quote/[^/]+/([^/?]+)")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Bind per-request context, time the handler, emit `request` event."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if _should_skip(path):
            return await call_next(request)

        request_id = uuid.uuid4().hex
        session_id = request.cookies.get(SESSION_COOKIE)
        step_name = _parse_step_name(path)
        settings = request.app.state.settings
        start = time.perf_counter()
        status = ERROR_STATUS
        with structlog.contextvars.bound_contextvars(
            request_id=request_id,
            session_id=session_id,
        ):
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
                    session_id=session_id,
                    step_name=step_name,
                    difficulty=settings.difficulty.value,
                    persona=settings.persona.value,
                )


def _should_skip(path: str) -> bool:
    if path in SKIP_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in SKIP_PREFIXES)


def _parse_step_name(path: str) -> str | None:
    """Return the `<step>` segment of `/quote/<sid>/<step>` paths.

    `start` and `submit` are intentionally filtered: `start` is the
    entry redirect that mints a fresh sid, and `submit` is the POST-only
    terminal endpoint. Neither corresponds to a renderable form step in
    plan section 13's step ladder, so they would muddy downstream
    `step_name` joins on request logs.
    """
    match = _QUOTE_STEP_RE.match(path)
    if match is None:
        return None
    step = match.group(1)
    if step in {"start", "submit"}:
        return None
    return step


__all__ = ["SESSION_COOKIE", "RequestLoggerMiddleware"]
