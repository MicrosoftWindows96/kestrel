"""CSRF service tests. HARD-only enforcement; EASY/MEDIUM are no-ops."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import structlog
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.csrf import (
    CSRF_COOKIE,
    CSRF_FORM_FIELD,
    CsrfService,
)
from kestrel.mock_site.middleware.challenge import FORCE_CHALLENGE_EVERY_ENV
from kestrel.mock_site.routes.challenge import CLEARANCE_COOKIE, mint_token

TEST_SEED = 20260510
TEST_SECRET = b"test" * 8

VEHICLE_FORM = {
    "vehicle_make": "Vauxhall",
    "vehicle_model": "Astra",
    "vehicle_year": "2018",
    "vehicle_value": "8500",
    "vehicle_fuel": "petrol",
    "vehicle_transmission": "manual",
}


def _settings(difficulty: Difficulty) -> Settings:
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
async def hard_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    """HARD app with intermittent disabled so CSRF tests are deterministic."""
    monkeypatch.delenv(FORCE_CHALLENGE_EVERY_ENV, raising=False)
    mock_logging.reset_for_tests()
    app = create_app(_settings(Difficulty.HARD))
    # Disable the intermittent roll so a single test stays on one page.
    app.state.intermittent_challenge_prob = 0.0
    async with LifespanManager(app):
        yield app


@pytest_asyncio.fixture
async def hard_client(hard_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=hard_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        # Seed a fresh clearance so /quote/* requests survive the gate.
        client.cookies.set(CLEARANCE_COOKIE, mint_token("placeholder", TEST_SECRET))
        yield client


@pytest_asyncio.fixture
async def easy_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(Difficulty.EASY))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client


@pytest_asyncio.fixture
async def medium_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(Difficulty.MEDIUM))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client


async def _start_session(client: httpx.AsyncClient) -> str:
    response = await client.get("/quote/start")
    assert response.status_code == 302
    return response.headers["location"].split("/")[2]


async def _start_session_and_seed_clearance(client: httpx.AsyncClient) -> str:
    sid = await _start_session(client)
    # The /quote/start handler does not require clearance but the next GET
    # would; refresh the clearance cookie to match the new sid.
    client.cookies.set(CLEARANCE_COOKIE, mint_token(sid, TEST_SECRET))
    return sid


async def _get_render_and_token(client: httpx.AsyncClient, sid: str) -> str:
    response = await client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 200, response.text
    # The same value that gets rendered in the hidden input and set as
    # the cookie should round-trip via the cookie jar.
    cookie_value = client.cookies.get(CSRF_COOKIE)
    assert cookie_value is not None, "CSRF cookie not set"
    assert cookie_value, "CSRF cookie empty"
    return cookie_value


async def test_hard_post_without_csrf_returns_403(hard_client: httpx.AsyncClient) -> None:
    sid = await _start_session_and_seed_clearance(hard_client)
    response = await hard_client.post(f"/quote/{sid}/vehicle", data=VEHICLE_FORM)
    assert response.status_code == 403


async def test_hard_post_with_wrong_csrf_returns_403(hard_client: httpx.AsyncClient) -> None:
    sid = await _start_session_and_seed_clearance(hard_client)
    await _get_render_and_token(hard_client, sid)
    payload = dict(VEHICLE_FORM, _csrf="bogus")
    response = await hard_client.post(f"/quote/{sid}/vehicle", data=payload)
    assert response.status_code == 403


async def test_hard_post_with_correct_csrf_succeeds(hard_client: httpx.AsyncClient) -> None:
    sid = await _start_session_and_seed_clearance(hard_client)
    token = await _get_render_and_token(hard_client, sid)
    payload = dict(VEHICLE_FORM, _csrf=token)
    response = await hard_client.post(f"/quote/{sid}/vehicle", data=payload)
    assert response.status_code in {200, 302}, response.text


async def test_hard_token_rotates_per_render(hard_client: httpx.AsyncClient) -> None:
    sid = await _start_session_and_seed_clearance(hard_client)
    first = await _get_render_and_token(hard_client, sid)
    second = await _get_render_and_token(hard_client, sid)
    assert first != second, "csrf token must rotate on every successful render"


async def test_hard_get_render_includes_non_empty_csrf_input(
    hard_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session_and_seed_clearance(hard_client)
    response = await hard_client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 200, response.text
    body = response.text
    assert f'name="{CSRF_FORM_FIELD}"' in body
    cookie_value = hard_client.cookies.get(CSRF_COOKIE)
    assert cookie_value is not None
    assert cookie_value in body


async def test_easy_post_without_csrf_succeeds(easy_client: httpx.AsyncClient) -> None:
    sid = await _start_session(easy_client)
    response = await easy_client.post(f"/quote/{sid}/vehicle", data=VEHICLE_FORM)
    assert response.status_code == 302, response.text


async def test_easy_get_renders_empty_csrf_input(easy_client: httpx.AsyncClient) -> None:
    sid = await _start_session(easy_client)
    response = await easy_client.get(f"/quote/{sid}/vehicle")
    body = response.text
    assert f'name="{CSRF_FORM_FIELD}" value=""' in body
    assert CSRF_COOKIE not in easy_client.cookies


async def test_medium_get_renders_empty_csrf_input(medium_client: httpx.AsyncClient) -> None:
    sid = await _start_session(medium_client)
    medium_client.cookies.set(CLEARANCE_COOKIE, mint_token(sid, TEST_SECRET))
    response = await medium_client.get(f"/quote/{sid}/vehicle")
    body = response.text
    assert f'name="{CSRF_FORM_FIELD}" value=""' in body
    assert CSRF_COOKIE not in medium_client.cookies


async def test_csrf_verify_is_not_middleware(hard_app: FastAPI) -> None:
    """`csrf_verify` is a Depends, not middleware - keep them distinct."""
    middleware_classes = [m.cls for m in hard_app.user_middleware]
    assert CsrfService not in middleware_classes
    middleware_names = [m.__name__ for m in middleware_classes]
    assert all("csrf" not in name.lower() for name in middleware_names)


async def test_csrf_mismatch_logs_session_and_step(
    hard_client: httpx.AsyncClient,
) -> None:
    """csrf_mismatch must carry session_id and step_name; no token bytes."""
    sid = await _start_session_and_seed_clearance(hard_client)
    await _get_render_and_token(hard_client, sid)
    with structlog.testing.capture_logs() as cap:
        response = await hard_client.post(
            f"/quote/{sid}/vehicle", data=dict(VEHICLE_FORM, _csrf="bogus")
        )
    assert response.status_code == 403
    mismatches = [entry for entry in cap if entry.get("event") == "csrf_mismatch"]
    assert mismatches, "expected csrf_mismatch event"
    payload = mismatches[-1]
    assert payload.get("session_id") == sid
    assert payload.get("step_name") == "vehicle"
    # Neither the cookie token nor the bogus form value should appear in
    # the captured payload.
    cookie_value = hard_client.cookies.get(CSRF_COOKIE)
    assert cookie_value is not None
    for value in payload.values():
        if isinstance(value, str):
            assert cookie_value not in value
            assert "bogus" not in value


async def test_csrf_cookie_attributes(hard_client: httpx.AsyncClient) -> None:
    sid = await _start_session_and_seed_clearance(hard_client)
    response = await hard_client.get(f"/quote/{sid}/vehicle")
    set_cookie = response.headers.get("set-cookie", "")
    csrf_header = next(
        (line for line in response.headers.get_list("set-cookie") if line.startswith(CSRF_COOKIE)),
        None,
    )
    assert csrf_header is not None, set_cookie
    assert "HttpOnly" in csrf_header
    assert "SameSite=strict" in csrf_header.lower() or "samesite=strict" in csrf_header.lower()
    assert "Path=/" in csrf_header
    # No Max-Age = session cookie; no Domain attribute by default.
    assert "Max-Age=" not in csrf_header
    assert "Domain=" not in csrf_header
    assert "Secure" not in csrf_header
    assert "Partitioned" not in csrf_header
