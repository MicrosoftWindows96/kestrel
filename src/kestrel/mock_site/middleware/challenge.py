"""Cloudflare-style wait-UX stub middleware.

This module is a wait-UX stub for the kestrel `wait_for_human` exercise.
It is NOT a Cloudflare emulator and NOT a circumvention tool. The mock
intentionally uses the cookie name `kestrel_clearance` (never
`cf_clearance`) and only paraphrased copy. No real Cloudflare endpoints
or assets are contacted.

EASY: pass through. MEDIUM: redirect when ``kestrel_clearance`` is
missing or stale. HARD: same initial-clearance check, plus a per-
request intermittent re-challenge roll keyed off the per-session
counter and the seeded ``app.state.intermittent_challenge_prob``. The
deterministic roll lets tests assert that the same seed produces the
same trigger sequence; ``KESTREL_MOCK_FORCE_CHALLENGE_EVERY=N`` (env
only, never CLI) overrides the roll to fire on every Nth gated request
so HARD tests avoid wallclock flakiness.
"""

from __future__ import annotations

import os
import random
from typing import Final

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from kestrel.mock_site.config import Difficulty
from kestrel.mock_site.routes.challenge import (
    CLEARANCE_COOKIE,
    TokenState,
    verify_token,
)

QUOTE_PREFIX: Final[str] = "/quote/"
START_PATH: Final[str] = "/quote/start"
CHALLENGE_REDIRECT_STATUS: Final[int] = 302
FORCE_CHALLENGE_EVERY_ENV: Final[str] = "KESTREL_MOCK_FORCE_CHALLENGE_EVERY"

_logger = structlog.get_logger("kestrel.mock_site.middleware.challenge")


class ChallengeMiddleware(BaseHTTPMiddleware):
    """Gate `/quote/<sid>/<step>` requests on a fresh clearance token.

    EASY: pass through. MEDIUM: missing or stale token redirects to
    `/challenge?next=<path>` and emits `challenge_emitted` (or
    `challenge_expired` for a recognised but stale token). HARD: same
    initial check plus a per-request intermittent re-challenge roll;
    when the roll fires the response also clears the existing clearance
    cookie so the gate stays armed until the user re-solves.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        settings = request.app.state.settings
        path = request.url.path
        if settings.difficulty is Difficulty.EASY:
            return await call_next(request)
        if not _is_gated_path(path):
            return await call_next(request)

        token = request.cookies.get(CLEARANCE_COOKIE)
        if token is None:
            return _redirect_to_challenge(
                request=request,
                target=path,
                event="challenge_emitted",
                sid=None,
            )

        state, sid = verify_token(token, settings.secret)
        if state is not TokenState.VALID:
            event = "challenge_expired" if state is TokenState.STALE else "challenge_emitted"
            return _redirect_to_challenge(
                request=request,
                target=path,
                event=event,
                sid=sid,
            )

        if settings.difficulty is Difficulty.HARD and _intermittent_fires(
            request=request, sid=sid or ""
        ):
            response = _redirect_to_challenge(
                request=request,
                target=path,
                event="challenge_emitted",
                sid=sid,
            )
            response.delete_cookie(CLEARANCE_COOKIE, path="/")
            return response

        return await call_next(request)


def _is_gated_path(path: str) -> bool:
    """Return True for `/quote/<sid>/<step>` paths only.

    `/quote/start` and `/quote/<sid>/submit` are excluded from the gate
    because the client cannot have obtained a clearance before the start
    redirect, and the submit POST is reached only after the full state
    is filled in via gated GETs and POSTs. Trailing slashes are
    normalised so a `/quote/<sid>/<step>/` request cannot bypass the
    gate.
    """
    if not path.startswith(QUOTE_PREFIX):
        return False
    normalised = path.rstrip("/") if path != "/" else path
    if normalised == START_PATH:
        return False
    parts = normalised.split("/")
    # ['', 'quote', '<sid>', '<step>'] -> exactly 4 parts; submit is
    # /quote/<sid>/submit and is reached via POST after the chain.
    if len(parts) != 4:
        return False
    return parts[3] not in {"submit", ""}


def _redirect_to_challenge(
    *,
    request: Request,
    target: str,
    event: str,
    sid: str | None,
) -> Response:
    settings = request.app.state.settings
    _logger.info(
        event,
        session_id=sid,
        difficulty=settings.difficulty.value,
        mode="auto",
    )
    return RedirectResponse(
        url=f"/challenge?next={target}",
        status_code=CHALLENGE_REDIRECT_STATUS,
    )


def _intermittent_fires(*, request: Request, sid: str) -> bool:
    """Return True when the HARD intermittent roll triggers re-challenge.

    Reads ``KESTREL_MOCK_FORCE_CHALLENGE_EVERY`` per-request (not at
    import) so tests can scope an override to a single ``monkeypatch``
    block. Without the override, draws from a deterministic RNG seeded
    on (sid, per-session counter, prob) so test runs are reproducible
    across processes. The per-session counter lives on
    ``app.state.session_request_counters`` and is pruned when the roll
    fires so the dict stays bounded by the active-session working set.
    """
    counters: dict[str, int] = request.app.state.session_request_counters
    counter = counters.get(sid, 0) + 1
    counters[sid] = counter

    force_every_raw = os.environ.get(FORCE_CHALLENGE_EVERY_ENV)
    if force_every_raw is not None:
        try:
            force_every = int(force_every_raw)
        except ValueError:
            force_every = 0
        if force_every > 0 and counter % force_every == 0:
            counters.pop(sid, None)
            return True
        return False

    prob: float = request.app.state.intermittent_challenge_prob
    seed = f"{sid}|{counter}|{prob:.6f}"
    rng = random.Random(seed)  # noqa: S311
    roll: float = rng.random()
    if roll < prob:
        counters.pop(sid, None)
        return True
    return False


__all__ = ["FORCE_CHALLENGE_EVERY_ENV", "ChallengeMiddleware"]
