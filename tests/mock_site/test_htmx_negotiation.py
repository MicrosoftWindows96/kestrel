"""HTMX fragment-vs-full-page negotiation prototype tests.

Phase B.5 prototype only. Section 10 deletes this module once the full
persona_c sweep covers the same invariants.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager
from bs4 import BeautifulSoup
from fastapi import FastAPI

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings

VALID_SID = "A" * 43


def _settings(difficulty: Difficulty) -> Settings:
    return Settings(
        difficulty=difficulty,
        persona=Persona.C,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=True,
        seed=20260510,
        secret=b"test" * 8,
        janitor_interval_seconds=86400,
        intermittent_challenge_prob=0.10,
    )


async def _build_client(
    difficulty: Difficulty,
) -> tuple[httpx.AsyncClient, FastAPI, LifespanManager]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(difficulty))
    manager = LifespanManager(app)
    await manager.__aenter__()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client, app, manager


@pytest_asyncio.fixture
async def client_persona_c_easy() -> AsyncIterator[httpx.AsyncClient]:
    client, _app, manager = await _build_client(Difficulty.EASY)
    try:
        yield client
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def client_persona_c_medium() -> AsyncIterator[httpx.AsyncClient]:
    client, _app, manager = await _build_client(Difficulty.MEDIUM)
    try:
        yield client
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def client_persona_c_hard() -> AsyncIterator[httpx.AsyncClient]:
    client, _app, manager = await _build_client(Difficulty.HARD)
    try:
        yield client
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


async def test_easy_returns_full_page_no_htmx(
    client_persona_c_easy: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_easy.get(f"/quote/{VALID_SID}/vehicle")
    assert response.status_code == 200
    body = response.text
    assert "<form" in body
    # The whole hx-* attribute namespace must be absent on EASY (not just
    # the few attrs the prototype currently uses).
    assert "hx-" not in body
    soup = BeautifulSoup(body, "html.parser")
    assert soup.find_all("script") == []


async def test_medium_returns_htmx_fragment(
    client_persona_c_medium: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_medium.get(f"/quote/{VALID_SID}/vehicle")
    assert response.status_code == 200
    body = response.text
    assert 'data-test-step="vehicle"' in body
    assert "hx-target" in body
    assert "hx-post" in body


async def test_hard_returns_htmx_fragment(
    client_persona_c_hard: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_hard.get(f"/quote/{VALID_SID}/vehicle")
    assert response.status_code == 200
    body = response.text
    assert 'data-test-step="vehicle"' in body
    assert "hx-target" in body
    assert "hx-post" in body


async def test_htmx_fragment_has_content_length_header(
    client_persona_c_medium: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_medium.get(f"/quote/{VALID_SID}/vehicle")
    headers_lower = {key.lower() for key in response.headers}
    assert "content-length" in headers_lower
    assert "transfer-encoding" not in headers_lower


async def test_htmx_fragment_has_hx_reswap_outerhtml(
    client_persona_c_medium: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_medium.get(f"/quote/{VALID_SID}/vehicle")
    assert response.headers.get("hx-reswap") == "outerHTML"


async def test_easy_fallback_no_htmx_min_js_reference(
    client_persona_c_easy: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_easy.get(f"/quote/{VALID_SID}/vehicle")
    body = response.text
    assert "/static/htmx" not in body
    assert "<script" not in body


async def test_data_test_step_vehicle_present(
    client_persona_c_medium: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_medium.get(f"/quote/{VALID_SID}/vehicle")
    assert 'data-test-step="vehicle"' in response.text


async def test_data_test_field_attrs_present(
    client_persona_c_medium: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_medium.get(f"/quote/{VALID_SID}/vehicle")
    body = response.text
    expected_fields = (
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_value",
        "vehicle_fuel",
        "vehicle_transmission",
    )
    for field in expected_fields:
        assert f"data-test-field-{field}" in body, f"missing data-test-field-{field}"
    soup = BeautifulSoup(body, "html.parser")
    inputs = soup.find_all(["input", "select"])
    field_inputs = [el for el in inputs if el.get("name", "").startswith("vehicle_")]
    assert field_inputs, "no vehicle_ inputs rendered"
    for el in field_inputs:
        assert "id" not in el.attrs, f"unexpected id on {el.get('name')}"


async def test_invalid_sid_returns_400(
    client_persona_c_medium: httpx.AsyncClient,
) -> None:
    response = await client_persona_c_medium.get("/quote/short/vehicle")
    assert response.status_code == 400


async def test_other_persona_returns_404() -> None:
    mock_logging.reset_for_tests()
    persona_a_settings = Settings(
        difficulty=Difficulty.MEDIUM,
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
    app = create_app(persona_a_settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/quote/{VALID_SID}/vehicle")
            assert response.status_code == 404
