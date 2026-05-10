"""Persona divergence axes from plan section 25.

Phase H1 activates persona_b across axes 1-9. Persona_c lands in
section 10. The tests pin the contract that downstream splits (and
the kestrel automation harness) rely on: stable selectors, persona-
distinct copy, currency format, error placement, and the field-id
strategy by difficulty.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from bs4 import BeautifulSoup
from bs4.element import Tag
from fastapi import FastAPI

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.csrf import CSRF_FORM_FIELD
from kestrel.mock_site.middleware.challenge import FORCE_CHALLENGE_EVERY_ENV
from kestrel.mock_site.routes.challenge import CLEARANCE_COOKIE, mint_token

TEST_SEED = 20260510
TEST_SECRET = b"test" * 8


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


async def _client_for(
    difficulty: Difficulty, persona: Persona
) -> tuple[httpx.AsyncClient, FastAPI, LifespanManager]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(difficulty, persona))
    # Disable intermittent re-challenge so HARD GETs do not bounce mid-test.
    app.state.intermittent_challenge_prob = 0.0
    manager = LifespanManager(app)
    await manager.__aenter__()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    )
    return client, app, manager


async def _start_with_clearance(client: httpx.AsyncClient) -> str:
    response = await client.get("/quote/start")
    assert response.status_code == 302
    sid = response.headers["location"].split("/")[2]
    client.cookies.set(CLEARANCE_COOKIE, mint_token(sid, TEST_SECRET))
    return sid


@pytest_asyncio.fixture
async def persona_b_easy(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    monkeypatch.delenv(FORCE_CHALLENGE_EVERY_ENV, raising=False)
    client, app, manager = await _client_for(Difficulty.EASY, Persona.B)
    try:
        yield client, app
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def persona_b_medium(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    monkeypatch.delenv(FORCE_CHALLENGE_EVERY_ENV, raising=False)
    client, app, manager = await _client_for(Difficulty.MEDIUM, Persona.B)
    try:
        yield client, app
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def persona_b_hard(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    monkeypatch.delenv(FORCE_CHALLENGE_EVERY_ENV, raising=False)
    client, app, manager = await _client_for(Difficulty.HARD, Persona.B)
    try:
        yield client, app
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


# Axis 1+4: container element + CSS class root


async def test_persona_b_root_form_class_is_legacy_form(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    form = soup.find("form", attrs={"data-test-step": "vehicle"})
    assert form is not None
    assert isinstance(form, Tag)
    assert "legacy-form" in form.get("class", [])


# Axis 5: submit button is an <input type="submit"> with value="Next"


async def test_persona_b_submit_is_input_next(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/vehicle")
    soup = BeautifulSoup(response.text, "html.parser")
    submit = soup.find(attrs={"data-test-submit": True})
    assert submit is not None
    assert isinstance(submit, Tag)
    assert submit.name == "input"
    assert submit.get("type") == "submit"
    assert submit.get("value") == "Next"


async def test_persona_b_review_submit_value(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/review?back=1")
    assert response.status_code == 200, response.text
    soup = BeautifulSoup(response.text, "html.parser")
    submit = soup.find(attrs={"data-test-submit": True})
    assert submit is not None
    assert isinstance(submit, Tag)
    assert submit.get("value") == "Get your price"


# Axis 3: field IDs by difficulty


async def test_persona_b_easy_field_ids_are_snake_case_stable(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/vehicle")
    soup = BeautifulSoup(response.text, "html.parser")
    field = soup.find(attrs={"name": "vehicle_make"})
    assert field is not None
    assert isinstance(field, Tag)
    assert field.get("id") == "vehicle_make"


async def test_persona_b_hard_field_ids_match_random_suffix_regex(
    persona_b_hard: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_hard
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/vehicle")
    soup = BeautifulSoup(response.text, "html.parser")
    field = soup.find(attrs={"name": "vehicle_make"})
    assert field is not None
    assert isinstance(field, Tag)
    fid = field.get("id")
    assert isinstance(fid, str)
    assert re.fullmatch(r"vehicle_make_[0-9a-f]{4}", fid), fid


async def test_persona_b_medium_field_ids_are_mixed(
    persona_b_medium: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_medium
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/vehicle")
    soup = BeautifulSoup(response.text, "html.parser")
    ids = {}
    for name in (
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_value",
        "vehicle_fuel",
        "vehicle_transmission",
    ):
        el = soup.find(attrs={"name": name})
        assert el is not None
        assert isinstance(el, Tag)
        fid = el.get("id")
        ids[name] = fid if isinstance(fid, str) else ""
    stable_count = sum(1 for name, fid in ids.items() if fid == name)
    suffixed_count = sum(
        1
        for name, fid in ids.items()
        if re.fullmatch(rf"{re.escape(name)}_[0-9a-f]{{4}}", fid)
    )
    assert stable_count >= 1, ids
    assert suffixed_count >= 1, ids


async def test_persona_b_hard_suffix_stable_per_session_and_step(
    persona_b_hard: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_hard
    sid = await _start_with_clearance(client)
    r1 = await client.get(f"/quote/{sid}/vehicle")
    r2 = await client.get(f"/quote/{sid}/vehicle")
    soup1 = BeautifulSoup(r1.text, "html.parser")
    soup2 = BeautifulSoup(r2.text, "html.parser")
    el1 = soup1.find(attrs={"name": "vehicle_make"})
    el2 = soup2.find(attrs={"name": "vehicle_make"})
    assert isinstance(el1, Tag)
    assert isinstance(el2, Tag)
    assert el1.get("id") == el2.get("id"), "suffix must be stable per (sid, step)"


async def test_persona_b_hard_suffix_differs_across_sessions(
    persona_b_hard: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_hard
    sid1 = await _start_with_clearance(client)
    r1 = await client.get(f"/quote/{sid1}/vehicle")
    client.cookies.clear()
    sid2 = await _start_with_clearance(client)
    r2 = await client.get(f"/quote/{sid2}/vehicle")
    el1 = BeautifulSoup(r1.text, "html.parser").find(attrs={"name": "vehicle_make"})
    el2 = BeautifulSoup(r2.text, "html.parser").find(attrs={"name": "vehicle_make"})
    assert isinstance(el1, Tag)
    assert isinstance(el2, Tag)
    assert el1.get("id") != el2.get("id"), "different sessions must yield different suffixes"


async def test_persona_b_hard_suffix_differs_across_steps(
    persona_b_hard: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_hard
    sid = await _start_with_clearance(client)
    r1 = await client.get(f"/quote/{sid}/vehicle")
    r2 = await client.get(f"/quote/{sid}/parking?back=1")
    el1 = BeautifulSoup(r1.text, "html.parser").find(attrs={"name": "vehicle_make"})
    el2 = BeautifulSoup(r2.text, "html.parser").find(attrs={"name": "parking_overnight"})
    assert isinstance(el1, Tag)
    assert isinstance(el2, Tag)
    fid1 = el1.get("id")
    fid2 = el2.get("id")
    assert isinstance(fid1, str)
    assert isinstance(fid2, str)
    # Different field on a different step must produce a different id.
    # The name prefix already differs; the regex also asserts the suffix
    # format so a downstream selector relying on the full id stays stable.
    assert fid1 != fid2
    assert re.fullmatch(r"vehicle_make_[0-9a-f]{4}", fid1)
    assert re.fullmatch(r"parking_overnight_[0-9a-f]{4}", fid2)


# Axes 6-9: error placement, quote-total markup, currency, form-error response


async def test_persona_b_error_placement_is_banner_at_top_of_form(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    response = await client.post(f"/quote/{sid}/vehicle", data={})
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    banner = soup.find("div", class_="banner banner-error")
    assert banner is not None
    assert isinstance(banner, Tag)
    error_spans = soup.find_all(attrs={"class": "field-error"})
    assert error_spans
    for span in error_spans:
        assert span.find_parent("div", class_="banner banner-error") is banner


async def test_persona_b_quote_total_markup_is_dl_dt_dd(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    await _drive_through_steps(client, sid)
    response = await client.post(f"/quote/{sid}/submit")
    assert response.status_code == 200, response.text
    soup = BeautifulSoup(response.text, "html.parser")
    dl = soup.find("dl", attrs={"data-test-quote-breakdown": True})
    assert dl is not None
    assert isinstance(dl, Tag)
    dt = dl.find("dt")
    assert dt is not None
    assert isinstance(dt, Tag)
    assert dt.get_text(strip=True) == "Total"
    total = dl.find("dd", attrs={"data-test-quote-total": True})
    assert total is not None
    assert isinstance(total, Tag)
    text = total.get_text(strip=True)
    assert text.startswith("£")
    # Persona_b currency: no thousands separator.
    assert "," not in text


async def test_persona_b_easy_renders_zero_script_tags(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    for step in (
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
    ):
        # `?back=1` bypasses the skip-ahead pointer so each step renders
        # regardless of stored form state, which is what we want here.
        response = await client.get(f"/quote/{sid}/{step}?back=1")
        assert response.status_code == 200, f"{step}: {response.text}"
        soup = BeautifulSoup(response.text, "html.parser")
        assert soup.find_all("script") == [], f"{step} rendered <script> in EASY"


async def test_persona_b_vehicle_mods_uses_htmx_on_medium(
    persona_b_medium: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_medium
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/vehicle-mods?back=1")
    assert response.status_code == 200, response.text
    body = response.text
    assert "hx-post" in body, "persona_b vehicle-mods MEDIUM must wire htmx"


VEHICLE = {
    "vehicle_make": "Vauxhall",
    "vehicle_model": "Astra",
    "vehicle_year": "2018",
    "vehicle_value": "8500",
    "vehicle_fuel": "petrol",
    "vehicle_transmission": "manual",
}
VEHICLE_MODS = {"vehicle_mods": "none"}
PARKING = {"parking_overnight": "driveway", "parking_daytime": "street"}
MILEAGE = {"annual_mileage": "8000", "business_use": "none"}
DRIVER_1 = {
    "driver_1_forename": "Alex",
    "driver_1_surname": "Smith",
    "driver_1_dob": "1990-04-01",
    "driver_1_licence_type": "full_uk",
    "driver_1_licence_held_since": "2010-04-01",
    "driver_1_occupation": "engineer",
    "driver_1_employment": "employed",
}
DRIVER_1_HISTORY = {"driver_1_claims": "[]", "driver_1_convictions": "[]"}
ADDITIONAL_DRIVERS = {"additional_driver_count": "0"}
ADDRESS = {
    "address_postcode": "SW1A 1AA",
    "address_line_1": "1 Example Street",
    "address_town": "Test Town",
}
COVER = {
    "cover_type": "fully_comp",
    "voluntary_excess": "250",
    "ncb_years": "5",
    "ncb_protection": "false",
    "addons": "breakdown",
}

_STEP_PAYLOADS: list[tuple[str, dict[str, str]]] = [
    ("vehicle", VEHICLE),
    ("vehicle-mods", VEHICLE_MODS),
    ("parking", PARKING),
    ("mileage", MILEAGE),
    ("driver-1", DRIVER_1),
    ("driver-1-history", DRIVER_1_HISTORY),
    ("additional-drivers", ADDITIONAL_DRIVERS),
    ("address", ADDRESS),
    ("cover", COVER),
]


async def _drive_through_steps(client: httpx.AsyncClient, sid: str) -> None:
    for step, payload in _STEP_PAYLOADS:
        response = await client.post(f"/quote/{sid}/{step}", data=payload)
        assert response.status_code in {200, 302}, f"{step}: {response.text}"


async def test_persona_b_full_easy_happy_path(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_easy
    sid = await _start_with_clearance(client)
    await _drive_through_steps(client, sid)
    submit = await client.post(f"/quote/{sid}/submit")
    assert submit.status_code == 200, submit.text
    assert "data-test-quote-total" in submit.text


@pytest_asyncio.fixture
async def persona_a_easy_client() -> AsyncIterator[httpx.AsyncClient]:
    mock_logging.reset_for_tests()
    app = create_app(_settings(Difficulty.EASY, Persona.A))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            yield client


async def test_persona_b_page_copy_distinct_from_persona_a(
    persona_b_easy: tuple[httpx.AsyncClient, FastAPI],
    persona_a_easy_client: httpx.AsyncClient,
) -> None:
    """Plan §25 axis: persona-styled page copy differs across personas."""
    b_client, _b_app = persona_b_easy
    b_sid = await _start_with_clearance(b_client)
    a_response = await persona_a_easy_client.get("/quote/start")
    a_sid = a_response.headers["location"].split("/")[2]

    distinct_pairs = 0
    for step in ("vehicle", "driver-1", "address"):
        a = await persona_a_easy_client.get(f"/quote/{a_sid}/{step}?back=1")
        b = await b_client.get(f"/quote/{b_sid}/{step}?back=1")
        assert a.status_code == 200, a.text
        assert b.status_code == 200, b.text
        a_title = BeautifulSoup(a.text, "html.parser").find("title")
        b_title = BeautifulSoup(b.text, "html.parser").find("title")
        assert isinstance(a_title, Tag)
        assert isinstance(b_title, Tag)
        a_text = a_title.get_text(strip=True)
        b_text = b_title.get_text(strip=True)
        if a_text != b_text:
            distinct_pairs += 1
    assert distinct_pairs >= 2, "persona_b copy must differ from persona_a on >= 2 steps"


async def test_persona_b_csrf_input_present_in_hard_render(
    persona_b_hard: tuple[httpx.AsyncClient, FastAPI],
) -> None:
    client, _app = persona_b_hard
    sid = await _start_with_clearance(client)
    response = await client.get(f"/quote/{sid}/vehicle")
    assert response.status_code == 200, response.text
    soup = BeautifulSoup(response.text, "html.parser")
    csrf_input = soup.find("input", attrs={"name": CSRF_FORM_FIELD})
    assert csrf_input is not None
    assert isinstance(csrf_input, Tag)
    value = csrf_input.get("value")
    assert isinstance(value, str), "HARD must render a string CSRF value"
    assert value, "HARD must render non-empty CSRF value"
