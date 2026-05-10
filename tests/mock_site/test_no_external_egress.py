"""Tests asserting the in-process app makes no non-loopback socket calls."""

from __future__ import annotations

import socket

import httpx
import pytest


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
