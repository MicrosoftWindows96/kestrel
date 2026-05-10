"""Pytest fixtures for mock-site tests.

Per plan section 17. The matrix product of Difficulty x Persona drives
the parametrized `app` fixture; client and settings fixtures derive from
it. Test seed and secret are deterministic so the seeded RNG draws
(intermittent challenge prob, future quote computation) are stable.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings

TEST_SEED = 20260510
TEST_SECRET = b"test" * 8
TEST_JANITOR_INTERVAL = 86400
TEST_INTERMITTENT_PROB = 0.10


def _matrix() -> list[tuple[Difficulty, Persona]]:
    return list(itertools.product(Difficulty, Persona))


@pytest.fixture(scope="session", params=_matrix(), ids=lambda p: f"{p[0].value}-{p[1].value}")
def difficulty_persona(request: pytest.FixtureRequest) -> tuple[Difficulty, Persona]:
    return cast(tuple[Difficulty, Persona], request.param)


@pytest.fixture(scope="session")
def difficulty(difficulty_persona: tuple[Difficulty, Persona]) -> Difficulty:
    return difficulty_persona[0]


@pytest.fixture(scope="session")
def persona(difficulty_persona: tuple[Difficulty, Persona]) -> Persona:
    return difficulty_persona[1]


@pytest.fixture(scope="session")
def settings(difficulty: Difficulty, persona: Persona) -> Settings:
    return Settings(
        difficulty=difficulty,
        persona=persona,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=True,
        seed=TEST_SEED,
        secret=TEST_SECRET,
        janitor_interval_seconds=TEST_JANITOR_INTERVAL,
        intermittent_challenge_prob=TEST_INTERMITTENT_PROB,
    )


@pytest_asyncio.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    mock_logging.reset_for_tests()
    fastapi_app = create_app(settings)
    async with LifespanManager(fastapi_app):
        yield fastapi_app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
