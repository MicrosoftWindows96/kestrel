"""EASY mode must render zero `<script>` tags across all personas.

Plan section 25 axis: EASY has no client-side JS so the kestrel adapter
exercises a degraded-but-functional rendering path that survives in the
oldest browsers and the bot-screening sandbox. Persona_c (section 10)
expands this file with a no-htmx fallback test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from bs4 import BeautifulSoup

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings

TEST_SEED = 20260510
TEST_SECRET = b"test" * 8

_STEPS: tuple[str, ...] = (
    "vehicle",
    "vehicle-mods",
    "parking",
    "mileage",
    "driver-1",
    "driver-1-history",
    "additional-drivers",
    "address",
    "cover",
    "review",
)


def _settings(persona: Persona) -> Settings:
    return Settings(
        difficulty=Difficulty.EASY,
        persona=persona,
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
async def persona_a_easy() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(Persona.A))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client


@pytest_asyncio.fixture
async def persona_b_easy() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(Persona.B))
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


@pytest.mark.parametrize("persona", ["persona_a", "persona_b"])
async def test_easy_renders_no_script_tags(
    persona_a_easy: httpx.AsyncClient,
    persona_b_easy: httpx.AsyncClient,
    persona: str,
) -> None:
    client = persona_a_easy if persona == "persona_a" else persona_b_easy
    sid = await _start_session(client)
    for step in _STEPS:
        response = await client.get(f"/quote/{sid}/{step}?back=1")
        assert response.status_code == 200, f"{persona}/{step}: {response.text}"
        soup = BeautifulSoup(response.text, "html.parser")
        scripts = soup.find_all("script")
        assert scripts == [], f"{persona}/{step} rendered <script> in EASY"
