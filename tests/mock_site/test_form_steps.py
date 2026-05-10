"""Form-step route tests for (EASY, persona_a). Phase E acceptance."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings

VALID_VEHICLE = {
    "vehicle_make": "Vauxhall",
    "vehicle_model": "Astra",
    "vehicle_year": "2018",
    "vehicle_value": "8500",
    "vehicle_fuel": "petrol",
    "vehicle_transmission": "manual",
}

VALID_VEHICLE_MODS = {"vehicle_mods": "none"}
VALID_PARKING = {"parking_overnight": "driveway", "parking_daytime": "street"}
VALID_MILEAGE = {"annual_mileage": "8000", "business_use": "none"}
VALID_DRIVER_1 = {
    "driver_1_forename": "Alex",
    "driver_1_surname": "Smith",
    "driver_1_dob": "1990-04-01",
    "driver_1_licence_type": "full_uk",
    "driver_1_licence_held_since": "2010-04-01",
    "driver_1_occupation": "engineer",
    "driver_1_employment": "employed",
}
VALID_DRIVER_1_HISTORY = {"driver_1_claims": "[]", "driver_1_convictions": "[]"}
VALID_ADDITIONAL_DRIVERS = {"additional_driver_count": "0"}
VALID_ADDRESS = {
    "address_postcode": "SW1A 1AA",
    "address_line_1": "1 Example Street",
    "address_town": "Test Town",
}
VALID_COVER = {
    "cover_type": "fully_comp",
    "voluntary_excess": "250",
    "ncb_years": "5",
    "ncb_protection": "false",
    "addons": "breakdown",
}
VALID_REVIEW: dict[str, str] = {}

STEP_PAYLOADS: list[tuple[str, dict[str, str]]] = [
    ("vehicle", VALID_VEHICLE),
    ("vehicle-mods", VALID_VEHICLE_MODS),
    ("parking", VALID_PARKING),
    ("mileage", VALID_MILEAGE),
    ("driver-1", VALID_DRIVER_1),
    ("driver-1-history", VALID_DRIVER_1_HISTORY),
    ("additional-drivers", VALID_ADDITIONAL_DRIVERS),
    ("address", VALID_ADDRESS),
    ("cover", VALID_COVER),
    ("review", VALID_REVIEW),
]


def _easy_persona_a_settings() -> Settings:
    return Settings(
        difficulty=Difficulty.EASY,
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


def _medium_persona_a_settings() -> Settings:
    return Settings(
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


@pytest_asyncio.fixture
async def easy_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_easy_persona_a_settings())
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client


@pytest_asyncio.fixture
async def medium_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_medium_persona_a_settings())
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
    assert location.startswith("/quote/")
    return location.split("/")[2]


async def test_quote_start_redirects_to_vehicle(easy_client: httpx.AsyncClient) -> None:
    response = await easy_client.get("/quote/start")
    assert response.status_code == 302
    assert response.headers["location"].endswith("/vehicle")
    cookie = response.headers.get("set-cookie", "")
    assert "kestrel_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/quote" in cookie


async def test_quote_start_with_existing_cookie_drops_state(
    easy_client: httpx.AsyncClient,
) -> None:
    first_sid = await _start_session(easy_client)
    second = await easy_client.get("/quote/start")
    assert second.status_code == 302
    new_sid = second.headers["location"].split("/")[2]
    assert new_sid != first_sid


async def test_get_vehicle_renders_persona_a_template(
    easy_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(easy_client)
    response = await easy_client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 200
    body = response.text
    assert 'data-test-step="vehicle"' in body
    assert 'class="aggregator-form"' in body
    assert 'name="_csrf"' in body
    assert 'value=""' in body  # empty CSRF in EASY


async def test_post_vehicle_valid_redirects_to_vehicle_mods(
    easy_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(easy_client)
    response = await easy_client.post(f"/quote/{sid}/vehicle", data=VALID_VEHICLE)
    assert response.status_code == 302
    assert response.headers["location"] == f"/quote/{sid}/vehicle-mods"


async def test_post_vehicle_invalid_rerenders_with_errors(
    easy_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(easy_client)
    bad = dict(VALID_VEHICLE)
    bad["vehicle_year"] = "not-a-year"
    response = await easy_client.post(f"/quote/{sid}/vehicle", data=bad)
    assert response.status_code == 200
    body = response.text
    assert "data-test-error-vehicle_year" in body


async def test_back_query_param_renders_existing_state(
    easy_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(easy_client)
    await easy_client.post(f"/quote/{sid}/vehicle", data=VALID_VEHICLE)
    response = await easy_client.get(f"/quote/{sid}/vehicle?back=1")
    assert response.status_code == 200
    assert "Vauxhall" in response.text


async def test_skip_ahead_blocked(easy_client: httpx.AsyncClient) -> None:
    sid = await _start_session(easy_client)
    await easy_client.post(f"/quote/{sid}/vehicle", data=VALID_VEHICLE)
    response = await easy_client.get(f"/quote/{sid}/cover")
    assert response.status_code == 302
    assert response.headers["location"] == f"/quote/{sid}/vehicle-mods"


async def test_url_sid_cookie_sid_mismatch_get_403(
    easy_client: httpx.AsyncClient,
) -> None:
    sid_a = await _start_session(easy_client)
    other_sid = "B" * 43
    # Cookie still pinned to sid_a; request a different sid in the URL.
    response = await easy_client.get(f"/quote/{other_sid}/vehicle")
    assert response.status_code == 403
    _ = sid_a


async def test_url_sid_cookie_sid_mismatch_post_403(
    easy_client: httpx.AsyncClient,
) -> None:
    sid_a = await _start_session(easy_client)
    other_sid = "B" * 43
    response = await easy_client.post(f"/quote/{other_sid}/vehicle", data=VALID_VEHICLE)
    assert response.status_code == 403
    _ = sid_a


async def test_csrf_token_rendered_empty_in_easy(
    easy_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(easy_client)
    response = await easy_client.get(f"/quote/{sid}/vehicle")
    assert '<input type="hidden" name="_csrf" value="">' in response.text


async def test_post_with_no_cookie_returns_403(easy_client: httpx.AsyncClient) -> None:
    sid = await _start_session(easy_client)
    # Drop the cookie jar to simulate a cookieless POST.
    easy_client.cookies.clear()
    response = await easy_client.post(f"/quote/{sid}/vehicle", data=VALID_VEHICLE)
    assert response.status_code == 403


async def test_empty_post_returns_required_errors(
    easy_client: httpx.AsyncClient,
) -> None:
    sid = await _start_session(easy_client)
    response = await easy_client.post(f"/quote/{sid}/vehicle", data={})
    assert response.status_code == 200
    body = response.text
    # Required-field invariant: every required slot emits a `<field>_required`
    # marker keyed off plan §13's closed set.
    for field in (
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_value",
        "vehicle_fuel",
        "vehicle_transmission",
    ):
        assert f"data-test-error-{field}" in body


async def test_full_10_step_happy_path(easy_client: httpx.AsyncClient) -> None:
    sid = await _start_session(easy_client)
    for step, payload in STEP_PAYLOADS[:-1]:
        response = await easy_client.post(f"/quote/{sid}/{step}", data=payload)
        assert response.status_code == 302, (
            f"{step} returned {response.status_code}: {response.text}"
        )
    submit = await easy_client.post(f"/quote/{sid}/submit")
    assert submit.status_code == 200, submit.text
    body = submit.text
    assert "data-test-quote-total" in body
    assert "data-test-quote-breakdown" in body


async def test_medium_challenge_interleave(medium_client: httpx.AsyncClient) -> None:
    sid = await _start_session(medium_client)
    redirect = await medium_client.get(f"/quote/{sid}/vehicle")
    assert redirect.status_code == 302
    assert redirect.headers["location"] == f"/challenge?next=/quote/{sid}/vehicle"
    solve = await medium_client.post(
        "/challenge/solve",
        json={"next": f"/quote/{sid}/vehicle"},
    )
    assert solve.status_code == 200
    landed = await medium_client.get(f"/quote/{sid}/vehicle")
    assert landed.status_code == 200, landed.text
    assert 'data-test-step="vehicle"' in landed.text
