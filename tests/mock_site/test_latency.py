"""LatencyMiddleware tests across all three difficulties.

Wallclock thresholds are loose so they remain green on a slow CI host.
The skip list is asserted by tight upper bounds on `/healthz`, `/static`,
and `/challenge/*` which must never see the artificial sleep.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.middleware.latency import PER_REQUEST_BUDGET_SECONDS

TEST_SEED = 20260510
TEST_SECRET = b"test" * 8
VALID_SID = "C" * 43


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


@pytest_asyncio.fixture
async def hard_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(Difficulty.HARD))
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


async def _measure(client: httpx.AsyncClient, url: str) -> float:
    started = time.perf_counter()
    await client.get(url)
    return time.perf_counter() - started


async def test_easy_overhead_minimal(easy_client: httpx.AsyncClient) -> None:
    sid = await _start_session(easy_client)
    elapsed = await _measure(easy_client, f"/quote/{sid}/vehicle")
    # Spec target is 10ms but the threshold is left at 100ms to absorb CI
    # contention; the spec bound is verified locally during dev work.
    assert elapsed < 0.10, f"EASY overhead too high: {elapsed:.3f}s"


async def test_medium_overhead_at_least_100ms(medium_client: httpx.AsyncClient) -> None:
    sid = await _start_session(medium_client)
    # First /quote/<sid>/vehicle redirects to /challenge under MEDIUM, but
    # the latency layer still fires before the redirect because /quote/* is
    # not in the skip list. uniform(0.10, 0.30) keeps this >=100ms.
    elapsed = await _measure(medium_client, f"/quote/{sid}/vehicle")
    assert elapsed >= 0.10, f"MEDIUM overhead too low: {elapsed:.3f}s"


async def test_hard_overhead_at_least_50ms(hard_client: httpx.AsyncClient) -> None:
    sid = await _start_session(hard_client)
    elapsed = await _measure(hard_client, f"/quote/{sid}/vehicle")
    assert elapsed >= 0.05, f"HARD overhead too low: {elapsed:.3f}s"


async def test_healthz_skipped(medium_client: httpx.AsyncClient) -> None:
    elapsed = await _measure(medium_client, "/healthz")
    assert elapsed < 0.05, f"/healthz should be skipped; got {elapsed:.3f}s"


async def test_readyz_skipped(medium_client: httpx.AsyncClient) -> None:
    elapsed = await _measure(medium_client, "/readyz")
    assert elapsed < 0.05, f"/readyz should be skipped; got {elapsed:.3f}s"


async def test_static_skipped(medium_client: httpx.AsyncClient) -> None:
    # The vendored htmx file lands in section 02; we only need a static
    # path lookup to confirm the prefix is in the skip list.
    elapsed = await _measure(medium_client, "/static/htmx.min.js")
    assert elapsed < 0.05, f"/static/* should be skipped; got {elapsed:.3f}s"


async def test_challenge_path_skipped(medium_client: httpx.AsyncClient) -> None:
    sid = await _start_session(medium_client)
    elapsed = await _measure(medium_client, f"/challenge?next=/quote/{sid}/vehicle")
    assert elapsed < 0.05, f"/challenge/* should be skipped; got {elapsed:.3f}s"


async def test_each_request_capped_by_per_request_budget(
    medium_client: httpx.AsyncClient,
) -> None:
    """Each leg honours the per-request cap; the chain test guards regression.

    The cap is per-request (Starlette builds a fresh ``Request`` per leg)
    so this asserts each individual leg stays under the budget rather
    than the cumulative chain wallclock.
    """
    sid = await _start_session(medium_client)

    leg1_start = time.perf_counter()
    redirect = await medium_client.get(f"/quote/{sid}/vehicle")
    leg1 = time.perf_counter() - leg1_start
    assert redirect.status_code == 302
    assert leg1 < PER_REQUEST_BUDGET_SECONDS, f"leg1 over budget: {leg1:.3f}s"

    leg2_start = time.perf_counter()
    solve = await medium_client.post(
        "/challenge/solve",
        json={"next": f"/quote/{sid}/vehicle"},
    )
    leg2 = time.perf_counter() - leg2_start
    assert solve.status_code == 200
    assert leg2 < PER_REQUEST_BUDGET_SECONDS, f"leg2 over budget: {leg2:.3f}s"

    leg3_start = time.perf_counter()
    final = await medium_client.get(f"/quote/{sid}/vehicle")
    leg3 = time.perf_counter() - leg3_start
    assert final.status_code == 200
    assert leg3 < PER_REQUEST_BUDGET_SECONDS, f"leg3 over budget: {leg3:.3f}s"


async def test_quote_trailing_slash_still_gated_under_medium(
    medium_client: httpx.AsyncClient,
) -> None:
    """Regression for I1: trailing slash must not bypass the challenge gate."""
    sid = await _start_session(medium_client)
    response = await medium_client.get(f"/quote/{sid}/vehicle/")
    assert response.status_code in {302, 307}
    if response.status_code == 302:
        assert response.headers["location"].startswith("/challenge")
