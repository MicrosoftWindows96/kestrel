"""Middleware-stack-order assertions.

Plan section 11 pins the final stack: RequestLogger (outermost) ->
Latency -> Challenge (innermost) -> handler. Starlette executes
middleware in reverse-registration order so the LAST `add_middleware`
call wraps the previous ones. CSRF is a `Depends`, not a middleware,
and must not appear in `app.user_middleware`.
"""

from __future__ import annotations

import pytest

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.csrf import CsrfService
from kestrel.mock_site.middleware.challenge import ChallengeMiddleware
from kestrel.mock_site.middleware.latency import LatencyMiddleware
from kestrel.mock_site.middleware.request_logger import (
    SESSION_COOKIE,
    SKIP_EXACT,
    SKIP_PREFIXES,
)


def _settings(difficulty: Difficulty = Difficulty.MEDIUM) -> Settings:
    return Settings(
        difficulty=difficulty,
        persona=Persona.A,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=True,
        seed=20260510,
        secret=b"test" * 8,
        janitor_interval_seconds=86400,
        intermittent_challenge_prob=0.10,
    )


@pytest.fixture
def app() -> object:
    mock_logging.reset_for_tests()
    return create_app(_settings())


def test_user_middleware_includes_three_classes(app: object) -> None:
    classes = [m.cls for m in app.user_middleware]  # type: ignore[attr-defined]
    assert ChallengeMiddleware in classes
    assert LatencyMiddleware in classes
    from kestrel.mock_site.middleware.request_logger import RequestLoggerMiddleware

    assert RequestLoggerMiddleware in classes


def test_outermost_is_request_logger(app: object) -> None:
    """Starlette's `add_middleware` prepends to `user_middleware`, so the
    LAST `add_middleware` call ends up at index 0 of the list. That entry
    is the outermost wrapper at request time.
    """
    from kestrel.mock_site.middleware.request_logger import RequestLoggerMiddleware

    head = app.user_middleware[0].cls  # type: ignore[attr-defined]
    assert head is RequestLoggerMiddleware


def test_innermost_is_challenge(app: object) -> None:
    tail = app.user_middleware[-1].cls  # type: ignore[attr-defined]
    assert tail is ChallengeMiddleware


def test_csrf_is_not_middleware(app: object) -> None:
    classes = [m.cls for m in app.user_middleware]  # type: ignore[attr-defined]
    assert CsrfService not in classes
    names = [m.__name__.lower() for m in classes]
    assert all("csrf" not in name for name in names)


def test_request_logger_skip_list_pinned() -> None:
    """Skip exact + prefix sets must include health, ready, static.

    Locking the set here keeps an accidental refactor that drops a
    prefix from breaking the production "no probes in logs" contract.
    """
    assert "/healthz" in SKIP_EXACT
    assert "/readyz" in SKIP_EXACT
    assert "/static" in SKIP_EXACT
    assert "/static/" in SKIP_PREFIXES


def test_latency_skip_list_pinned() -> None:
    from kestrel.mock_site.middleware import latency

    skip_prefixes = latency._SKIP_PREFIXES
    for required in ("/healthz", "/readyz", "/static", "/challenge"):
        assert required in skip_prefixes, f"missing latency skip prefix: {required}"


def test_request_logger_session_cookie_name_pinned() -> None:
    assert SESSION_COOKIE == "kestrel_session"
