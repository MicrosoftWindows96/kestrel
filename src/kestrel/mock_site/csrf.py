"""CSRF service. `Depends`-injectable on POST routes; no-op outside HARD.

Plan section 11.4 / section 22 pinned decision: CSRF is a dependency,
not middleware, because middleware fires on every GET, every static
asset, and every health probe; the protection only needs to fire on
state-mutating POST routes. The class lives in this module instead of
``middleware/`` so that distinction stays visible at the import path.

Token format mirrors the section-07 ``kestrel_clearance`` scheme:

    base64url(struct.pack(">I", len(sid_bytes))
              + sid_bytes
              + struct.pack(">Q", ts)
              + hmac_sha256_digest)

The explicit length prefix defends against HMAC malleability; an
attacker swapping a longer sid for a shorter one with the same first
bytes would fail the prefix check before the digest comparison.

Verification routes through ``hmac.compare_digest`` only and returns
``HTTPException(403)`` on any mismatch, with a ``csrf_mismatch`` log
event carrying ``session_id`` and ``step_name`` (no token bytes,
no provided value).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass
from typing import Annotated, Final

import structlog
from fastapi import Depends, HTTPException, Request, Response

from kestrel.mock_site.config import Difficulty, Settings

CSRF_COOKIE: Final[str] = "kestrel_csrf"
CSRF_FORM_FIELD: Final[str] = "_csrf"
_DIGEST_LEN: Final[int] = hashlib.sha256().digest_size
_LEN_PREFIX_LEN: Final[int] = 4
_TIMESTAMP_LEN: Final[int] = 8
_MIN_TOKEN_BYTES: Final[int] = _LEN_PREFIX_LEN + _TIMESTAMP_LEN + _DIGEST_LEN

_logger = structlog.get_logger("kestrel.mock_site.csrf")


@dataclass(frozen=True, slots=True)
class CsrfService:
    """Token mint + verify hooks. EASY/MEDIUM short-circuit to empty token."""

    secret: bytes

    def mint(self, request: Request) -> str:
        """Return a fresh CSRF token, or ``""`` outside HARD.

        Callers mint before rendering the template so the hidden form
        field carries the same value the cookie will. The cookie itself
        is applied by ``set_cookie`` once the response object exists.
        """
        settings: Settings = request.app.state.settings
        if settings.difficulty is not Difficulty.HARD:
            return ""
        sid = self._sid_for(request)
        return _mint_token(sid, self.secret)

    @staticmethod
    def set_cookie(response: Response, token: str) -> None:
        """Apply the §7 cookie attribute table for ``kestrel_csrf``.

        ``secure=False`` is intentional: the mock binds 127.0.0.1 only
        and ``Secure=True`` would make the cookie undeliverable to the
        test transport or the loopback browser.
        """
        if not token:
            return
        response.set_cookie(
            key=CSRF_COOKIE,
            value=token,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
        )

    def issue(self, request: Request, response: Response) -> str:
        """Convenience: mint the token and apply the cookie in one call.

        Under HARD a fresh token is minted on every call so every
        successful render rotates the cookie. Outside HARD this returns
        ``""`` and does not touch the cookie so the EASY/MEDIUM hidden
        inputs render with an empty value, matching the section-06
        contract.
        """
        token = self.mint(request)
        self.set_cookie(response, token)
        return token

    async def verify(self, request: Request, *, step_name: str) -> None:
        """Verify the form ``_csrf`` field matches the cookie via compare_digest.

        Raises ``HTTPException(403)`` on any mismatch (missing cookie,
        missing form field, value mismatch, or HMAC integrity failure).
        Emits ``csrf_mismatch`` with ``session_id`` and ``step_name``;
        no token bytes or provided value are logged.
        """
        cookie_token = request.cookies.get(CSRF_COOKIE)
        form = await request.form()
        form_token = form.get(CSRF_FORM_FIELD)
        sid = self._sid_for(request)
        form_value = form_token if isinstance(form_token, str) else None
        if (
            cookie_token is None
            or form_value is None
            or not hmac.compare_digest(cookie_token, form_value)
            or not _verify_token_integrity(form_value, self.secret)
        ):
            _logger.info("csrf_mismatch", session_id=sid, step_name=step_name)
            raise HTTPException(status_code=403, detail="csrf token mismatch")

    @staticmethod
    def _sid_for(request: Request) -> str:
        """Derive the sid for the token; URL path takes precedence over cookie.

        The HMAC payload is bound to a sid so two distinct sessions cannot
        cross-replay a captured token. Falls back to the session cookie or
        an empty string when neither is present (e.g. issue from a route
        that has no sid).
        """
        path_sid = request.path_params.get("sid")
        if isinstance(path_sid, str) and path_sid:
            return path_sid
        cookie_sid = request.cookies.get("kestrel_session")
        return cookie_sid or ""


def _mint_token(sid: str, secret: bytes, *, now: int | None = None) -> str:
    sid_bytes = sid.encode("utf-8")
    # ns resolution avoids token collisions when two renders happen inside the
    # same wallclock second; CSRF tokens have no expiry check so the field is
    # purely a freshness nonce.
    ts = now if now is not None else time.time_ns()
    payload = struct.pack(">I", len(sid_bytes)) + sid_bytes + struct.pack(">Q", ts)
    digest = hmac.new(secret, payload, hashlib.sha256).digest()
    raw = payload + digest
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _verify_token_integrity(token: str, secret: bytes) -> bool:
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + padding)
    except (ValueError, TypeError):
        return False
    if len(raw) < _MIN_TOKEN_BYTES:
        return False
    sid_len = struct.unpack(">I", raw[:_LEN_PREFIX_LEN])[0]
    expected_total = _LEN_PREFIX_LEN + sid_len + _TIMESTAMP_LEN + _DIGEST_LEN
    if len(raw) != expected_total:
        return False
    payload = raw[: _LEN_PREFIX_LEN + sid_len + _TIMESTAMP_LEN]
    digest = raw[_LEN_PREFIX_LEN + sid_len + _TIMESTAMP_LEN :]
    expected = hmac.new(secret, payload, hashlib.sha256).digest()
    return hmac.compare_digest(digest, expected)


def get_csrf_service(request: Request) -> CsrfService:
    service: CsrfService = request.app.state.csrf_service
    return service


async def csrf_verify(
    request: Request,
    csrf: Annotated[CsrfService, Depends(get_csrf_service)],
) -> None:
    """FastAPI dependency. No-op outside HARD; section 08 fills HARD."""
    settings: Settings = request.app.state.settings
    if settings.difficulty is not Difficulty.HARD:
        return
    step = request.path_params.get("step")
    step_name = step if isinstance(step, str) else "<unknown>"
    await csrf.verify(request, step_name=step_name)


__all__ = [
    "CSRF_COOKIE",
    "CSRF_FORM_FIELD",
    "CsrfService",
    "csrf_verify",
    "get_csrf_service",
]
