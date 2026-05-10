"""Tests asserting the in-process app makes no non-loopback socket calls."""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest

# Hosts a real production page might contact; mock-site renders must not.
_THIRD_PARTY_HOSTS: tuple[str, ...] = (
    "cloudflare.com",
    "challenges.cloudflare.com",
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
    "facebook.com",
    "twitter.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
)


async def test_socket_connect_refuses_nonloopback_in_process(
    monkeypatch: pytest.MonkeyPatch, client: httpx.AsyncClient
) -> None:
    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: tuple[str, int]) -> None:
        host = address[0] if isinstance(address, tuple) else None
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise PermissionError(f"egress to {host!r} forbidden in tests")
        real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    response = await client.get("/healthz")
    assert response.status_code == 200


async def test_rendered_html_has_no_third_party_host_refs(
    client: httpx.AsyncClient,
) -> None:
    """Run across the parametrized 9 (difficulty, persona) combos via conftest."""
    response = await client.get("/quote/start")
    assert response.status_code in {200, 302}, response.text
    sid = response.headers.get("location", "/").split("/")[2] if response.status_code == 302 else ""
    body = response.text or ""
    if sid:
        # Pull one step page to widen the sweep; persona_c MEDIUM/HARD returns
        # a bare fragment but the host-ref check is identical.
        step = await client.get(f"/quote/{sid}/vehicle?back=1")
        if step.status_code in {200, 302}:
            body = f"{body}\n{step.text}"
    lower = body.lower()
    for host in _THIRD_PARTY_HOSTS:
        assert host not in lower, f"third-party host leaked: {host}"


def test_vendored_htmx_has_no_third_party_host_refs() -> None:
    """Vendored htmx.min.js must not call out to a third-party CDN.

    Any reference to a third-party host, including the canonical
    `unpkg.com/htmx` attribution comment, fails the check. The mock
    site must serve the asset entirely from its own static mount.
    """
    asset = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "kestrel"
        / "mock_site"
        / "static"
        / "htmx.min.js"
    )
    if not asset.exists():
        pytest.skip("htmx.min.js placeholder not yet committed")
    text = asset.read_text(encoding="utf-8", errors="ignore").lower()
    for host in _THIRD_PARTY_HOSTS:
        assert host not in text, f"vendored htmx references {host}"
