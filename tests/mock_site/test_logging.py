"""Tests for the request logger middleware (Phase A scope only)."""

from __future__ import annotations

import contextlib
import io
import json
import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import structlog
from asgi_lifespan import LifespanManager

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings

REQUIRED_FIELDS = frozenset(
    {
        "event",
        "method",
        "path",
        "status",
        "duration_ms",
        "request_id",
        "session_id",
        "step_name",
        "difficulty",
        "persona",
    }
)


def _build_settings(*, quiet: bool = False) -> Settings:
    return Settings(
        difficulty=Difficulty.MEDIUM,
        persona=Persona.A,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=quiet,
        seed=20260510,
        secret=b"test" * 8,
        janitor_interval_seconds=86400,
        intermittent_challenge_prob=0.10,
    )


@pytest.fixture(autouse=True)
def _reset_logging_each_test() -> Iterator[None]:
    mock_logging.reset_for_tests()
    yield
    mock_logging.reset_for_tests()


@pytest_asyncio.fixture
async def fresh_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(_build_settings())
    async with LifespanManager(app) as mgr:
        transport = httpx.ASGITransport(app=mgr.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest_asyncio.fixture
async def easy_client() -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        difficulty=Difficulty.EASY,
        persona=Persona.A,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=False,
        seed=20260510,
        secret=b"test" * 8,
        janitor_interval_seconds=86400,
        intermittent_challenge_prob=0.0,
    )
    app = create_app(settings)
    async with LifespanManager(app) as mgr:
        transport = httpx.ASGITransport(app=mgr.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as c:
            yield c


async def test_request_event_emits_required_fields(
    fresh_client: httpx.AsyncClient,
) -> None:
    with structlog.testing.capture_logs() as cap:
        response = await fresh_client.get("/_does_not_exist")
        assert response.status_code == 404
    events = [entry for entry in cap if entry.get("event") == "request"]
    assert events, "expected at least one `request` event"
    payload = events[-1]
    missing = REQUIRED_FIELDS - payload.keys()
    assert not missing, f"missing fields: {sorted(missing)}"


async def test_request_id_is_uuid4_hex_per_request(
    fresh_client: httpx.AsyncClient,
) -> None:
    with structlog.testing.capture_logs() as cap:
        await fresh_client.get("/_a")
        await fresh_client.get("/_b")
    ids = [entry["request_id"] for entry in cap if entry.get("event") == "request"]
    assert len(ids) == 2
    assert ids[0] != ids[1]
    for rid in ids:
        assert len(rid) == 32
        int(rid, 16)


async def test_x_request_id_header_ignored(
    fresh_client: httpx.AsyncClient,
) -> None:
    with structlog.testing.capture_logs() as cap:
        await fresh_client.get("/_x", headers={"X-Request-Id": "supplied-by-client"})
    events = [entry for entry in cap if entry.get("event") == "request"]
    assert events
    assert events[-1]["request_id"] != "supplied-by-client"


def test_quiet_silences_request_events() -> None:
    mock_logging.configure_logging(quiet=True, log_file=None, json_renderer=True)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        structlog.get_logger("kestrel.mock_site.request").info(
            "request",
            method="GET",
            path="/x",
            status=200,
            duration_ms=1.0,
        )
    rendered = buf.getvalue()
    for line in filter(None, rendered.splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        assert payload.get("event") != "request"


def test_log_file_receives_request_event(tmp_path: Path) -> None:
    """`--log-file` must capture structlog events; previously broken via stdlib gap."""
    log_file = tmp_path / "events.log"
    mock_logging.configure_logging(quiet=False, log_file=log_file, json_renderer=True)
    structlog.get_logger("kestrel.mock_site.request").info(
        "request",
        method="GET",
        path="/x",
        status=200,
        duration_ms=1.5,
    )
    # Force flush the rotating handler (FileHandler buffers per-record on most platforms).
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = log_file.read_text(encoding="utf-8")
    assert text.strip(), "log file is empty; structlog never reached the file handler"
    payload = json.loads(text.splitlines()[0])
    assert payload["event"] == "request"
    assert payload["method"] == "GET"


def test_structlog_module_level_no_double_configure() -> None:
    settings = _build_settings()
    create_app(settings)
    assert mock_logging.is_configured()
    create_app(settings)
    assert mock_logging.is_configured()


async def test_bound_contextvars_clears_per_request(
    fresh_client: httpx.AsyncClient,
) -> None:
    structlog.contextvars.clear_contextvars()
    await fresh_client.get("/_c")
    leftover = structlog.contextvars.get_contextvars()
    assert "request_id" not in leftover
    assert "session_id" not in leftover


async def test_validation_failure_carries_error_key_no_provided_value(
    easy_client: httpx.AsyncClient,
) -> None:
    """`validation_failure` must surface `error_key` and never the rejected input."""
    fresh_client = easy_client
    start = await fresh_client.get("/quote/start", follow_redirects=False)
    sid = start.headers["location"].split("/")[2]
    bad_postcode = "Q1 2AB"  # invalid - Q is not a valid first-letter
    # Drive the form to the address step so the validator fires on its field.
    valid_steps = [
        (
            "vehicle",
            {
                "vehicle_make": "Vauxhall",
                "vehicle_model": "Astra",
                "vehicle_year": "2018",
                "vehicle_value": "8500",
                "vehicle_fuel": "petrol",
                "vehicle_transmission": "manual",
            },
        ),
        ("vehicle-mods", {"vehicle_mods": "none"}),
        ("parking", {"parking_overnight": "driveway", "parking_daytime": "street"}),
        ("mileage", {"annual_mileage": "8000", "business_use": "none"}),
        (
            "driver-1",
            {
                "driver_1_forename": "Alex",
                "driver_1_surname": "Smith",
                "driver_1_dob": "1990-04-01",
                "driver_1_licence_type": "full_uk",
                "driver_1_licence_held_since": "2010-04-01",
                "driver_1_occupation": "engineer",
                "driver_1_employment": "employed",
            },
        ),
        ("driver-1-history", {"driver_1_claims": "[]", "driver_1_convictions": "[]"}),
        ("additional-drivers", {"additional_driver_count": "0"}),
    ]
    for step, payload in valid_steps:
        await fresh_client.post(f"/quote/{sid}/{step}", data=payload)
    with structlog.testing.capture_logs() as cap:
        bad = await fresh_client.post(
            f"/quote/{sid}/address",
            data={
                "address_postcode": bad_postcode,
                "address_line_1": "1 Example Street",
                "address_town": "Test Town",
            },
        )
        assert bad.status_code == 200
    failures = [entry for entry in cap if entry.get("event") == "validation_failure"]
    assert failures, "expected validation_failure event"
    payload = failures[-1]
    assert payload.get("session_id") == sid
    assert payload.get("step_name") == "address"
    assert payload.get("field_name") == "address_postcode"
    assert "error_key" in payload
    # Critical: the rejected input must NEVER appear anywhere in the payload.
    for value in payload.values():
        if isinstance(value, str):
            assert bad_postcode not in value


async def test_quote_computed_event_payload(easy_client: httpx.AsyncClient) -> None:
    """`quote_computed` event fires on submit and carries pence-resolution total."""
    fresh_client = easy_client
    start = await fresh_client.get("/quote/start", follow_redirects=False)
    sid = start.headers["location"].split("/")[2]
    steps = [
        (
            "vehicle",
            {
                "vehicle_make": "Vauxhall",
                "vehicle_model": "Astra",
                "vehicle_year": "2018",
                "vehicle_value": "8500",
                "vehicle_fuel": "petrol",
                "vehicle_transmission": "manual",
            },
        ),
        ("vehicle-mods", {"vehicle_mods": "none"}),
        ("parking", {"parking_overnight": "driveway", "parking_daytime": "street"}),
        ("mileage", {"annual_mileage": "8000", "business_use": "none"}),
        (
            "driver-1",
            {
                "driver_1_forename": "Alex",
                "driver_1_surname": "Smith",
                "driver_1_dob": "1990-04-01",
                "driver_1_licence_type": "full_uk",
                "driver_1_licence_held_since": "2010-04-01",
                "driver_1_occupation": "engineer",
                "driver_1_employment": "employed",
            },
        ),
        ("driver-1-history", {"driver_1_claims": "[]", "driver_1_convictions": "[]"}),
        ("additional-drivers", {"additional_driver_count": "0"}),
        (
            "address",
            {
                "address_postcode": "SW1A 1AA",
                "address_line_1": "1 Example Street",
                "address_town": "Test Town",
            },
        ),
        (
            "cover",
            {
                "cover_type": "fully_comp",
                "voluntary_excess": "250",
                "ncb_years": "5",
                "ncb_protection": "false",
                "addons": "breakdown",
            },
        ),
    ]
    for step, payload in steps:
        await fresh_client.post(f"/quote/{sid}/{step}", data=payload)
    with structlog.testing.capture_logs() as cap:
        submit = await fresh_client.post(f"/quote/{sid}/submit")
        assert submit.status_code == 200, submit.text
    quotes = [entry for entry in cap if entry.get("event") == "quote_computed"]
    assert quotes, "expected quote_computed event"
    payload = quotes[-1]
    assert payload.get("session_id") == sid
    assert payload.get("persona") == "persona_a"
    total_pence = payload.get("total_premium_pence")
    assert isinstance(total_pence, int)
    assert total_pence > 0


async def test_state_transition_field_names_is_frozenset(
    easy_client: httpx.AsyncClient,
) -> None:
    """Plan section 16 pins `field_names` as a `frozenset[str]` payload."""
    fresh_client = easy_client
    start = await fresh_client.get("/quote/start", follow_redirects=False)
    sid = start.headers["location"].split("/")[2]
    with structlog.testing.capture_logs() as cap:
        await fresh_client.post(
            f"/quote/{sid}/vehicle",
            data={
                "vehicle_make": "Vauxhall",
                "vehicle_model": "Astra",
                "vehicle_year": "2018",
                "vehicle_value": "8500",
                "vehicle_fuel": "petrol",
                "vehicle_transmission": "manual",
            },
        )
    transitions = [entry for entry in cap if entry.get("event") == "state_transition"]
    assert transitions
    payload = transitions[-1]
    assert payload.get("session_id") == sid
    assert payload.get("step_name") == "vehicle"
    field_names = payload.get("field_names")
    assert isinstance(field_names, frozenset)
    assert "vehicle_make" in field_names


async def test_skipped_paths_emit_no_request_event(
    fresh_client: httpx.AsyncClient,
) -> None:
    with structlog.testing.capture_logs() as cap:
        for path in ("/healthz", "/readyz", "/static/htmx.min.js"):
            await fresh_client.get(path)
    requests = [entry for entry in cap if entry.get("event") == "request"]
    assert requests == [], requests
