"""Challenge stub route + middleware tests (MEDIUM scope; HARD in section 08)."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.routes.challenge import (
    CLEARANCE_COOKIE,
    CLEARANCE_MAX_AGE,
    NEXT_PATH_RE,
    TokenState,
    mint_token,
    sanitize_next,
    verify_token,
)

VALID_SID = "A" * 43
TEST_SECRET = b"test" * 8
TEST_SEED = 20260510


def _build_settings(difficulty: Difficulty) -> Settings:
    return Settings(
        difficulty=difficulty,
        persona=Persona.A,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=True,
        seed=TEST_SEED,
        secret=TEST_SECRET,
        janitor_interval_seconds=86400,
        intermittent_challenge_prob=0.10,
    )


@pytest_asyncio.fixture
async def easy_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_build_settings(Difficulty.EASY))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client


@pytest_asyncio.fixture
async def medium_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_build_settings(Difficulty.MEDIUM))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client


async def _start_session(client: httpx.AsyncClient) -> str:
    response = await client.get("/quote/start")
    assert response.status_code == 302
    location = response.headers["location"]
    return location.split("/")[2]


async def test_easy_no_challenge_fires(easy_client: httpx.AsyncClient) -> None:
    sid = await _start_session(easy_client)
    response = await easy_client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 200, response.text
    assert "kestrel-challenge" not in response.text


async def test_medium_redirects_when_clearance_missing(
    medium_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(medium_client)
    response = await medium_client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 302
    assert response.headers["location"] == f"/challenge?next=/quote/{sid}/vehicle"


async def test_clearance_cookie_name_is_kestrel_not_cf(
    medium_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(medium_client)
    redirect = await medium_client.get(f"/quote/{sid}/vehicle")
    assert redirect.status_code == 302
    solve = await medium_client.post(
        "/challenge/solve",
        json={"next": f"/quote/{sid}/vehicle"},
    )
    assert solve.status_code == 200
    set_cookie = solve.headers.get("set-cookie", "")
    assert f"{CLEARANCE_COOKIE}=" in set_cookie
    assert "cf_clearance" not in set_cookie.lower()


async def test_challenge_html_paraphrases_copy(medium_client: httpx.AsyncClient) -> None:
    sid = await _start_session(medium_client)
    response = await medium_client.get(f"/challenge?next=/quote/{sid}/vehicle")
    assert response.status_code == 200
    body = response.text
    assert "Verifying you are human" in body
    # CF's exact phrase. Mock must paraphrase, not copy.
    assert "Checking your browser before accessing" not in body


async def test_challenge_html_has_kestrel_challenge_meta(
    medium_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(medium_client)
    response = await medium_client.get(f"/challenge?next=/quote/{sid}/vehicle")
    assert '<meta name="kestrel-challenge" content="active">' in response.text


async def test_challenge_html_has_test_active_attribute(
    medium_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(medium_client)
    response = await medium_client.get(f"/challenge?next=/quote/{sid}/vehicle")
    assert "data-test-challenge-active" in response.text


async def test_challenge_html_has_no_third_party_assets(
    medium_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(medium_client)
    response = await medium_client.get(f"/challenge?next=/quote/{sid}/vehicle")
    body = response.text.lower()
    assert "cloudflare.com" not in body
    assert "challenges.cloudflare.com" not in body


async def test_post_solve_sets_clearance_cookie(medium_client: httpx.AsyncClient) -> None:
    sid = await _start_session(medium_client)
    response = await medium_client.post(
        "/challenge/solve",
        json={"next": f"/quote/{sid}/vehicle"},
    )
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert f"{CLEARANCE_COOKIE}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert f"Max-Age={CLEARANCE_MAX_AGE}" in set_cookie


def test_token_format_is_hmac_sha256_struct_packed_golden() -> None:
    """Golden vector: pin the token shape so future refactors cannot drift."""
    sid = VALID_SID
    secret = b"x" * 32
    fixed_ts = 1_700_000_000
    token = mint_token(sid, secret, now=fixed_ts)
    head, ts_str, digest = token.split("|", 2)
    assert head == sid
    assert ts_str == str(fixed_ts)
    # Reconstruct expected digest deterministically; if either the digest
    # algorithm or the struct-packed length prefix changes, this breaks.
    import hashlib
    import struct

    sid_bytes = sid.encode("utf-8")
    msg = struct.pack(">I", len(sid_bytes)) + sid_bytes + struct.pack(">Q", fixed_ts)
    expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    assert digest == expected


def test_verify_token_uses_constant_time_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke-check that verification routes through `hmac.compare_digest`."""
    calls: list[tuple[str, str]] = []
    real_compare = hmac.compare_digest

    def spy(a: object, b: object) -> bool:
        calls.append((str(a), str(b)))
        return real_compare(a, b)  # type: ignore[arg-type]

    monkeypatch.setattr("kestrel.mock_site.routes.challenge.hmac.compare_digest", spy)
    sid = VALID_SID
    token = mint_token(sid, TEST_SECRET, now=1_700_000_000)
    state, recovered = verify_token(token, TEST_SECRET, now=1_700_000_000)
    assert state is TokenState.VALID
    assert recovered == sid
    assert calls, "compare_digest was not called"


def test_verify_token_stale_returns_state_stale() -> None:
    sid = VALID_SID
    token = mint_token(sid, TEST_SECRET, now=1_000_000_000)
    state, recovered = verify_token(token, TEST_SECRET, now=1_000_000_000 + 2_000)
    assert state is TokenState.STALE
    assert recovered == sid


async def test_stale_token_redirects_back_to_challenge(
    medium_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(medium_client)
    # Mint a token from far in the past so the age check rejects it.
    stale = mint_token(sid, TEST_SECRET, now=1_000_000_000)
    medium_client.cookies.set(CLEARANCE_COOKIE, stale, domain="test")
    response = await medium_client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 302
    assert response.headers["location"] == f"/challenge?next=/quote/{sid}/vehicle"


@pytest.mark.parametrize(
    "next_value",
    [
        "https://evil.com",
        "//evil.com",
        "///evil.com",
        f"/quote/{VALID_SID}/vehicle/../etc/passwd",
        "/quote/short/vehicle",
        "/quote/" + ("A" * 43) + "/unknown-step",
        "/quote/" + ("A" * 43) + "\\/vehicle",
    ],
)
async def test_get_challenge_rejects_bad_next(
    medium_client: httpx.AsyncClient, next_value: str
) -> None:
    response = await medium_client.get(f"/challenge?next={next_value}")
    assert response.status_code == 400


async def test_manual_mode_renders_button_and_no_auto_fire(
    medium_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(medium_client)
    response = await medium_client.get(f"/challenge?manual=1&next=/quote/{sid}/vehicle")
    assert response.status_code == 200
    body = response.text
    assert "data-test-challenge-solve-button" in body
    # Auto-fire timer must not appear in the manual-mode HTML.
    assert "setTimeout(" not in body


async def test_request_after_solve_is_allowed(medium_client: httpx.AsyncClient) -> None:
    sid = await _start_session(medium_client)
    solve = await medium_client.post(
        "/challenge/solve",
        json={"next": f"/quote/{sid}/vehicle"},
    )
    assert solve.status_code == 200
    response = await medium_client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 200, response.text


def test_sanitize_next_accepts_canonical_path() -> None:
    target = f"/quote/{VALID_SID}/vehicle"
    assert sanitize_next(target) == target
    assert NEXT_PATH_RE.fullmatch(target) is not None


@pytest.mark.parametrize(
    "bad",
    [
        "",
        None,
        "https://evil.com",
        "//evil.com",
        "///evil.com",
        f"/quote/{VALID_SID}/vehicle/../etc/passwd",
        f"/quote/{VALID_SID}/vehicle\\extra",
    ],
)
def test_sanitize_next_rejects_bad_inputs(bad: str | None) -> None:
    assert sanitize_next(bad) is None
