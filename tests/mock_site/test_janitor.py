"""Tests for the async janitor task."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta

import pytest

from kestrel.mock_site.state.janitor import run_janitor
from kestrel.mock_site.state.memory import InMemorySessionStore


class _CountingStore(InMemorySessionStore):
    def __init__(self) -> None:
        super().__init__()
        self.gc_calls: int = 0
        self.fail_next: bool = False

    async def gc(self, older_than: timedelta) -> int:
        self.gc_calls += 1
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("synthetic gc failure")
        return await super().gc(older_than)


@pytest.mark.slow
async def test_janitor_sleeps_first_then_ticks() -> None:
    store = _CountingStore()
    task = asyncio.create_task(run_janitor(store, interval_seconds=0.05))
    try:
        # Immediately after start the first tick has not fired yet.
        await asyncio.sleep(0.01)
        assert store.gc_calls == 0
        # After enough wall time, multiple ticks land.
        await asyncio.sleep(0.2)
        assert store.gc_calls >= 3
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.slow
async def test_janitor_swallows_gc_exception_and_keeps_running() -> None:
    store = _CountingStore()
    store.fail_next = True
    task = asyncio.create_task(run_janitor(store, interval_seconds=0.02))
    try:
        await asyncio.sleep(0.1)
        # First tick raised, but the loop kept ticking afterwards.
        assert store.gc_calls >= 2
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.slow
async def test_janitor_cancellation_re_raises() -> None:
    store = _CountingStore()
    task = asyncio.create_task(run_janitor(store, interval_seconds=0.05))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
