"""Challenge routes.

Phase F: render the wait-UX page on GET and mint a clearance cookie on
POST. NOT a Cloudflare emulator and NOT a circumvention tool; all copy
is paraphrased and no third-party assets are referenced. The token
format and cookie attribute table are pinned in plan section 7 and
plan section 11.3.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import re
import struct
import time
from enum import Enum
from typing import Annotated, Final
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError

from kestrel.mock_site.config import Difficulty

CLEARANCE_COOKIE: Final[str] = "kestrel_clearance"
CLEARANCE_MAX_AGE: Final[int] = 1800

DELAY_MS_EASY: Final[int] = 0
DELAY_MS_MEDIUM: Final[int] = 2500
DELAY_MS_HARD_MEAN: Final[int] = 7500
DELAY_MS_HARD_STDEV: Final[int] = 1000
DELAY_MS_HARD_MIN: Final[int] = 6000
DELAY_MS_HARD_MAX: Final[int] = 9000

NEXT_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"^/quote/[A-Za-z0-9_-]{43}/"
    r"(?:vehicle|vehicle-mods|parking|mileage|driver-1|driver-1-history|"
    r"additional-drivers|address|cover|review)$"
)

router = APIRouter(prefix="/challenge", tags=["challenge"])
_logger = structlog.get_logger("kestrel.mock_site.routes.challenge")


class _SolveBody(BaseModel):
    """JSON body for fetch-driven solve. Manual mode uses form-encoded body."""

    next: str = Field(..., min_length=1, max_length=512)


class TokenState(Enum):
    """Outcome of `verify_token`. Distinguishes stale from malformed."""

    VALID = "valid"
    STALE = "stale"
    INVALID = "invalid"


def mint_token(sid: str, secret: bytes, *, now: int | None = None) -> str:
    """Build the `sid|ts|hex(hmac)` token per plan section 11.3.

    The HMAC payload prefixes the sid bytes with `struct.pack(">I",
    len(sid_bytes))` so a same-secret attacker cannot alias two distinct
    sids by collision on the `|` delimiter.
    """
    sid_bytes = sid.encode("utf-8")
    ts = now if now is not None else int(time.time())
    msg = struct.pack(">I", len(sid_bytes)) + sid_bytes + struct.pack(">Q", ts)
    digest = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return f"{sid}|{ts}|{digest}"


def verify_token(
    token: str,
    secret: bytes,
    *,
    max_age: int = CLEARANCE_MAX_AGE,
    now: int | None = None,
) -> tuple[TokenState, str | None]:
    """Verify a clearance token. Returns (state, sid_if_recoverable).

    `compare_digest` defends against timing leaks. Stale tokens still
    surface their sid so the middleware can emit `challenge_expired`.
    """
    parts = token.split("|", 2)
    if len(parts) != 3:
        return TokenState.INVALID, None
    sid, ts_str, digest_hex = parts
    if not sid or not ts_str or not digest_hex:
        return TokenState.INVALID, None
    try:
        ts = int(ts_str)
    except ValueError:
        return TokenState.INVALID, None
    sid_bytes = sid.encode("utf-8")
    msg = struct.pack(">I", len(sid_bytes)) + sid_bytes + struct.pack(">Q", ts)
    expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest_hex, expected):
        return TokenState.INVALID, None
    current = now if now is not None else int(time.time())
    if current - ts >= max_age:
        return TokenState.STALE, sid
    return TokenState.VALID, sid


def sanitize_next(value: str | None) -> str | None:
    """Return the validated `next` path, or None if rejected.

    Reject any URL with a scheme, netloc, leading `//`, backslash, or
    `..` segment. After those, demand the closed-set quote-step regex
    so the redirect target is always a known intra-app path.
    """
    if not isinstance(value, str) or not value:
        return None
    if "\\" in value:
        return None
    if value.startswith("//"):
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return None
    if ".." in parsed.path.split("/"):
        return None
    if not NEXT_PATH_RE.fullmatch(value):
        return None
    return value


def delay_ms_for(difficulty: Difficulty, rng: random.Random) -> int:
    """Auto-fire delay per difficulty per plan section 11.3."""
    if difficulty is Difficulty.EASY:
        return DELAY_MS_EASY
    if difficulty is Difficulty.MEDIUM:
        return DELAY_MS_MEDIUM
    raw = rng.gauss(DELAY_MS_HARD_MEAN, DELAY_MS_HARD_STDEV)
    clamped = max(DELAY_MS_HARD_MIN, min(DELAY_MS_HARD_MAX, raw))
    return int(clamped)


def set_clearance_cookie(response: Response, token: str) -> None:
    """Apply the §7 cookie attribute table to `response`.

    `secure=False` is intentional: the mock binds 127.0.0.1 only and a
    Secure cookie would not be deliverable to the test transport or the
    loopback browser.
    """
    response.set_cookie(
        CLEARANCE_COOKIE,
        token,
        max_age=CLEARANCE_MAX_AGE,
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
    )


@router.get("", response_class=HTMLResponse)
async def get_challenge(
    request: Request,
    next_path: Annotated[str, Query(alias="next")],
    manual: int = 0,
) -> Response:
    """Render the wait-UX page or 400 if `next` fails the whitelist."""
    sanitized = sanitize_next(next_path)
    if sanitized is None:
        raise HTTPException(status_code=400, detail="invalid next parameter")
    settings = request.app.state.settings
    rng_seed = settings.seed
    rng = random.Random(rng_seed)  # noqa: S311
    delay_ms = delay_ms_for(settings.difficulty, rng)
    templates = request.app.state.templates
    response: HTMLResponse = templates.TemplateResponse(
        request,
        "challenge.html",
        {
            "next": sanitized,
            "delay_ms": delay_ms,
            "manual": bool(manual),
        },
    )
    return response


@router.post("/solve")
async def post_challenge_solve(request: Request) -> Response:
    """Verify next, mint a clearance token, set cookie, return JSON or redirect.

    Supports JSON body (auto-fire fetch) and form-encoded body (manual
    fallback form post). The response shape matches the request's
    content-type so a JS client gets `{next}` and a no-JS client gets
    a 303 redirect.
    """
    content_type = request.headers.get("content-type", "")
    is_json = "application/json" in content_type
    next_value: str | None
    if is_json:
        try:
            data = await request.json()
            body = _SolveBody.model_validate(data)
            next_value = body.next
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="invalid json body") from None
    else:
        form = await request.form()
        raw = form.get("next")
        next_value = raw if isinstance(raw, str) else None

    sanitized = sanitize_next(next_value)
    if sanitized is None:
        raise HTTPException(status_code=400, detail="invalid next parameter")

    sid_match = NEXT_PATH_RE.fullmatch(sanitized)
    if sid_match is None:  # pragma: no cover - guarded by sanitize_next
        raise HTTPException(status_code=400, detail="invalid next parameter")
    sid = sanitized.split("/")[2]

    settings = request.app.state.settings
    token = mint_token(sid, settings.secret)

    if is_json:
        response: Response = JSONResponse({"next": sanitized})
    else:
        response = RedirectResponse(url=sanitized, status_code=303)
    set_clearance_cookie(response, token)

    _logger.info(
        "challenge_solved",
        session_id=sid,
        difficulty=settings.difficulty.value,
    )
    return response


__all__ = [
    "CLEARANCE_COOKIE",
    "CLEARANCE_MAX_AGE",
    "NEXT_PATH_RE",
    "TokenState",
    "delay_ms_for",
    "mint_token",
    "router",
    "sanitize_next",
    "set_clearance_cookie",
    "verify_token",
]
