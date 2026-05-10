"""Tests for the vendored htmx asset, license, and integrity hash."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import structlog

STATIC_DIR = Path(__file__).resolve().parents[2] / "src" / "kestrel" / "mock_site" / "static"
HTMX_FILE = STATIC_DIR / "htmx.min.js"
HTMX_SHA = STATIC_DIR / "htmx.sha256"
HTMX_LICENSE = STATIC_DIR / "LICENSE.htmx"
REQUEST_LOGGER_NAMESPACE = "kestrel.mock_site.request"


def test_htmx_file_exists_and_nonempty() -> None:
    assert HTMX_FILE.exists()
    size = HTMX_FILE.stat().st_size
    assert size > 0
    assert size > 10_000, f"htmx.min.js looks like a placeholder; got {size} bytes"


def test_sha256_matches_hash_file() -> None:
    expected = HTMX_SHA.read_text(encoding="utf-8").strip().lower()
    actual = hashlib.sha256(HTMX_FILE.read_bytes()).hexdigest().lower()
    assert actual == expected


def test_license_present_and_marks_bsd_family() -> None:
    assert HTMX_LICENSE.exists(), "LICENSE.htmx missing alongside vendored asset"
    text = HTMX_LICENSE.read_text(encoding="utf-8")
    assert "BSD" in text or "0BSD" in text, "license file lacks BSD/0BSD marker"


async def test_static_htmx_route_returns_200_with_js_content_type(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/static/htmx.min.js")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "javascript" in content_type, f"unexpected Content-Type: {content_type!r}"


async def test_static_htmx_response_has_no_set_cookie(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/static/htmx.min.js")
    assert "set-cookie" not in {key.lower() for key in response.headers}


async def test_static_htmx_request_emits_no_log(
    client: httpx.AsyncClient,
) -> None:
    with structlog.testing.capture_logs() as cap:
        await client.get("/static/htmx.min.js")
    request_events = [entry for entry in cap if entry.get("logger") == REQUEST_LOGGER_NAMESPACE]
    assert request_events == []
