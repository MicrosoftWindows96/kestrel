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
