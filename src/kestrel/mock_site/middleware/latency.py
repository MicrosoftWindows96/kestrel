"""Per-difficulty artificial-latency middleware.

Plan section 11.4. Parameters are read from `settings` only, never from
request data; the RNG is freshly seeded from `settings.seed` per dispatch
so concurrent coroutines do not share mutable RNG state. Health,
readiness, static, and challenge paths are exempt so probes and the
wait-UX page remain snappy and so the latency cost does not double-count
when the gate redirects to `/challenge`.

Per-request cap: each dispatch initialises ``request.state`` with a
budget of ``PER_REQUEST_BUDGET_SECONDS`` and clamps the drawn sleep to
the remaining budget. The cap is intentionally per-request, not
per-redirect-chain; ``request.state`` resets on every inbound request
because Starlette constructs a fresh ``Request`` per leg.
"""

from __future__ import annotations

import asyncio
import random
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from kestrel.mock_site.config import Difficulty, Settings

PER_REQUEST_BUDGET_SECONDS: Final[float] = 1.0
LATENCY_BUDGET_STATE_KEY: Final[str] = "latency_budget_remaining"

_SKIP_PREFIXES: Final[tuple[str, ...]] = (
    "/healthz",
    "/readyz",
    "/static",
    "/challenge",
)

_MEDIUM_MIN_SECONDS: Final[float] = 0.10
_MEDIUM_MAX_SECONDS: Final[float] = 0.30
_HARD_MEAN_SECONDS: Final[float] = 0.40
_HARD_STDEV_SECONDS: Final[float] = 0.20
_HARD_MIN_SECONDS: Final[float] = 0.05
_HARD_MAX_SECONDS: Final[float] = 0.80


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class LatencyMiddleware(BaseHTTPMiddleware):
    """Sleep before downstream handler runs based on `settings.difficulty`.

    Constructed once per app and supplied with a `settings` handle by the
    factory. The RNG is rebuilt per dispatch from `settings.seed` so a
    test run sees reproducible draws and concurrent requests do not race
    on a shared RNG state.
    """

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings: Settings = settings

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if _should_skip(path):
            return await call_next(request)

        settings = self._settings
        rng = random.Random(settings.seed)  # noqa: S311
        budget_remaining = getattr(
            request.state, LATENCY_BUDGET_STATE_KEY, PER_REQUEST_BUDGET_SECONDS
        )

        sleep_seconds = _draw_sleep(rng, settings.difficulty)
        clamped = max(0.0, min(sleep_seconds, budget_remaining))
        if clamped > 0.0:
            await asyncio.sleep(clamped)
            budget_remaining -= clamped
        setattr(request.state, LATENCY_BUDGET_STATE_KEY, budget_remaining)

        return await call_next(request)


def _draw_sleep(rng: random.Random, difficulty: Difficulty) -> float:
    if difficulty is Difficulty.EASY:
        return 0.0
    if difficulty is Difficulty.MEDIUM:
        return rng.uniform(_MEDIUM_MIN_SECONDS, _MEDIUM_MAX_SECONDS)
    return _clamp(
        rng.gauss(_HARD_MEAN_SECONDS, _HARD_STDEV_SECONDS),
        _HARD_MIN_SECONDS,
        _HARD_MAX_SECONDS,
    )


def _should_skip(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _SKIP_PREFIXES)


__all__ = [
    "LATENCY_BUDGET_STATE_KEY",
    "PER_REQUEST_BUDGET_SECONDS",
    "LatencyMiddleware",
]
