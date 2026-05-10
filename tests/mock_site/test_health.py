"""Tests for /healthz and /readyz."""

from __future__ import annotations

import httpx
import structlog

REQUEST_LOGGER_NAMESPACE = "kestrel.mock_site.request"


async def test_healthz_200_every_combo(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_200_every_combo(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthz_no_log(client: httpx.AsyncClient) -> None:
    with structlog.testing.capture_logs() as cap:
        await client.get("/healthz")
    # Filter on logger namespace so a regression that emits any event from the
    # request logger (under any name) for skipped paths still trips the assert.
    request_events = [entry for entry in cap if entry.get("logger") == REQUEST_LOGGER_NAMESPACE]
    assert request_events == []


async def test_readyz_no_log(client: httpx.AsyncClient) -> None:
    with structlog.testing.capture_logs() as cap:
        await client.get("/readyz")
    request_events = [entry for entry in cap if entry.get("logger") == REQUEST_LOGGER_NAMESPACE]
    assert request_events == []
