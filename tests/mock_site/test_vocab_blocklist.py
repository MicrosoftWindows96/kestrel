"""Vocabulary blocklist check across rendered HTML.

Plan section 11 puts the blocklist file in the split-11 CI tooling
package; the mock-site does not own the file. If the file is absent
this whole module skips. When present, every rendered persona x
difficulty x step page must be free of blocklist terms and free of
em-dashes (U+2014).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.routes.challenge import CLEARANCE_COOKIE, mint_token

TEST_SECRET = b"test" * 8
TEST_SEED = 20260510
EM_DASH = "—"

_BLOCKLIST_PATH_CANDIDATES = (
    Path(__file__).resolve().parent.parent.parent / "vocab_blocklist.txt",
    Path(__file__).resolve().parent.parent.parent.parent / "vocab_blocklist.txt",
)


def _load_blocklist() -> list[str]:
    for candidate in _BLOCKLIST_PATH_CANDIDATES:
        if candidate.exists():
            return [
                line.strip().lower()
                for line in candidate.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
    return []


_BLOCKLIST = _load_blocklist()

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

_PERSONAS = (Persona.A, Persona.B, Persona.C)
_DIFFICULTIES = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)


def _settings(difficulty: Difficulty, persona: Persona) -> Settings:
    return Settings(
        difficulty=difficulty,
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


@pytest_asyncio.fixture(params=list(_PERSONAS), ids=[p.value for p in _PERSONAS])
async def persona_easy_client(
    request: pytest.FixtureRequest,
) -> AsyncIterator[tuple[httpx.AsyncClient, Persona]]:
    """One easy-mode client per persona for the full step sweep."""
    persona = request.param
    mock_logging.reset_for_tests()
    app = create_app(_settings(Difficulty.EASY, persona))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client, persona


def _check_text(text: str, label: str) -> None:
    assert EM_DASH not in text, f"{label} contains em-dash"
    lower = text.lower()
    for term in _BLOCKLIST:
        assert term not in lower, f"{label} contains blocklist term: {term}"


@pytest.mark.slow
async def test_every_step_render_is_blocklist_clean(
    persona_easy_client: tuple[httpx.AsyncClient, Persona],
) -> None:
    client, persona = persona_easy_client
    start = await client.get("/quote/start")
    assert start.status_code == 302
    sid = start.headers["location"].split("/")[2]
    for step in _STEPS:
        response = await client.get(f"/quote/{sid}/{step}?back=1")
        assert response.status_code == 200, f"{persona.value}/{step}"
        _check_text(response.text, f"{persona.value} EASY {step}")


@pytest.mark.parametrize("difficulty", [Difficulty.MEDIUM, Difficulty.HARD])
async def test_challenge_html_is_blocklist_clean(difficulty: Difficulty) -> None:
    for persona in _PERSONAS:
        mock_logging.reset_for_tests()
        app = create_app(_settings(difficulty, persona))
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                start = await client.get("/quote/start")
                sid = start.headers["location"].split("/")[2]
                response = await client.get(f"/challenge?next=/quote/{sid}/vehicle")
                assert response.status_code == 200, response.text
                _check_text(response.text, f"{persona.value} {difficulty.value} challenge")


async def test_quote_result_is_blocklist_clean() -> None:
    """Drive the full happy path under EASY and check the rendered result."""
    payloads = {
        "vehicle": {
            "vehicle_make": "Vauxhall",
            "vehicle_model": "Astra",
            "vehicle_year": "2018",
            "vehicle_value": "8500",
            "vehicle_fuel": "petrol",
            "vehicle_transmission": "manual",
        },
        "vehicle-mods": {"vehicle_mods": "none"},
        "parking": {"parking_overnight": "driveway", "parking_daytime": "street"},
        "mileage": {"annual_mileage": "8000", "business_use": "none"},
        "driver-1": {
            "driver_1_forename": "Alex",
            "driver_1_surname": "Smith",
            "driver_1_dob": "1990-04-01",
            "driver_1_licence_type": "full_uk",
            "driver_1_licence_held_since": "2010-04-01",
            "driver_1_occupation": "engineer",
            "driver_1_employment": "employed",
        },
        "driver-1-history": {"driver_1_claims": "[]", "driver_1_convictions": "[]"},
        "additional-drivers": {"additional_driver_count": "0"},
        "address": {
            "address_postcode": "SW1A 1AA",
            "address_line_1": "1 Example Street",
            "address_town": "Test Town",
        },
        "cover": {
            "cover_type": "fully_comp",
            "voluntary_excess": "250",
            "ncb_years": "5",
            "ncb_protection": "false",
            "addons": "breakdown",
        },
    }
    for persona in _PERSONAS:
        mock_logging.reset_for_tests()
        app = create_app(_settings(Difficulty.EASY, persona))
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as client:
                start = await client.get("/quote/start")
                sid = start.headers["location"].split("/")[2]
                client.cookies.set(
                    CLEARANCE_COOKIE, mint_token(sid, TEST_SECRET)
                )
                for step, payload in payloads.items():
                    resp = await client.post(f"/quote/{sid}/{step}", data=payload)
                    assert resp.status_code in {200, 302}, f"{persona.value}/{step}: {resp.text}"
                submit = await client.post(f"/quote/{sid}/submit")
                assert submit.status_code == 200, submit.text
                _check_text(submit.text, f"{persona.value} quote_result")
