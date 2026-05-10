"""Tests for `InMemorySessionStore`."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from kestrel.mock_site.state.memory import InMemorySessionStore
from kestrel.mock_site.state.models import FormState, VehicleStep


@pytest.fixture
def state() -> FormState:
    return FormState(vehicle=VehicleStep(vehicle_make="Vauxhall"))


async def test_put_then_get_returns_same_state(state: FormState) -> None:
    store = InMemorySessionStore()
    await store.put("sid-1", state)
    got = await store.get("sid-1")
    assert got is not None
    assert got.model_dump() == state.model_dump()


async def test_get_missing_returns_none() -> None:
    store = InMemorySessionStore()
    assert await store.get("nope") is None


async def test_delete_removes_entry(state: FormState) -> None:
    store = InMemorySessionStore()
    await store.put("sid-1", state)
    await store.delete("sid-1")
    assert await store.get("sid-1") is None


async def test_delete_unknown_sid_no_raise() -> None:
    store = InMemorySessionStore()
    await store.delete("does-not-exist")


async def test_gc_removes_old_entries_only(state: FormState) -> None:
    store = InMemorySessionStore()
    await store.put("fresh", state)
    await store.put("stale", state)
    # Backdate the "stale" entry by mutating the internal dict directly. Safe
    # only because no other coroutine touches the store between the two awaits
    # above and the gc call below; do not copy this pattern into tests that
    # spawn concurrent workers.
    backdated = datetime.now(UTC) - timedelta(hours=1)
    store._data["stale"] = (state, backdated)  # type: ignore[attr-defined]
    removed = await store.gc(timedelta(minutes=30))
    assert removed == 1
    assert await store.get("fresh") is not None
    assert await store.get("stale") is None


async def test_gc_returns_zero_when_nothing_old(state: FormState) -> None:
    store = InMemorySessionStore()
    await store.put("fresh", state)
    removed = await store.gc(timedelta(hours=1))
    assert removed == 0


async def test_close_is_noop() -> None:
    store = InMemorySessionStore()
    await store.close()
    await store.close()


async def test_concurrent_put_get_no_corruption(state: FormState) -> None:
    store = InMemorySessionStore()

    async def worker(i: int) -> None:
        sid = f"sid-{i}"
        await store.put(sid, state)
        got = await store.get(sid)
        assert got is not None

    await asyncio.gather(*(worker(i) for i in range(50)))
    for i in range(50):
        assert await store.get(f"sid-{i}") is not None
