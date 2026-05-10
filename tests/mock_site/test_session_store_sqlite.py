"""Tests for `SqliteSessionStore` happy path + lifecycle."""

from __future__ import annotations

import os
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.state.models import FormState, VehicleStep
from kestrel.mock_site.state.sqlite import SqliteSessionStore
from kestrel.mock_site.state.store import (
    DEFAULT_SQLITE_FILENAME,
    StoreInitError,
    make_session_store,
)

SECRET = b"test" * 8


def _make_settings(difficulty: Difficulty = Difficulty.HARD) -> Settings:
    return Settings(
        difficulty=difficulty,
        persona=Persona.A,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=True,
        seed=20260510,
        secret=SECRET,
        janitor_interval_seconds=86400,
        intermittent_challenge_prob=0.10,
    )


def _create_db_file(tmp_path: Path) -> Path:
    db_path = tmp_path / DEFAULT_SQLITE_FILENAME
    fd = os.open(str(db_path), os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    return db_path


@pytest.fixture
def state() -> FormState:
    return FormState(vehicle=VehicleStep(vehicle_make="Vauxhall"))


async def test_put_then_get_returns_same_state(tmp_path: Path, state: FormState) -> None:
    db_path = _create_db_file(tmp_path)
    store = SqliteSessionStore(db_path)
    try:
        await store.put("sid-1", state)
        got = await store.get("sid-1")
        assert got is not None
        assert got.model_dump() == state.model_dump()
    finally:
        await store.close()


async def test_delete_removes_entry(tmp_path: Path, state: FormState) -> None:
    db_path = _create_db_file(tmp_path)
    store = SqliteSessionStore(db_path)
    try:
        await store.put("sid-1", state)
        await store.delete("sid-1")
        assert await store.get("sid-1") is None
    finally:
        await store.close()


async def test_gc_removes_old_entries(tmp_path: Path, state: FormState) -> None:
    db_path = _create_db_file(tmp_path)
    store = SqliteSessionStore(db_path)
    try:
        await store.put("stale", state)
        # Backdate the row so gc with a tiny threshold removes it.
        conn = await store._connection()  # type: ignore[attr-defined]
        await conn.execute("UPDATE sessions SET updated_at = 0 WHERE sid = ?", ("stale",))
        await conn.commit()

        await store.put("fresh", state)
        removed = await store.gc(timedelta(seconds=1))
        assert removed == 1
        assert await store.get("stale") is None
        assert await store.get("fresh") is not None
    finally:
        await store.close()


async def test_state_survives_close_and_recreate(tmp_path: Path, state: FormState) -> None:
    db_path = _create_db_file(tmp_path)
    store = SqliteSessionStore(db_path)
    await store.put("durable", state)
    await store.close()

    again = SqliteSessionStore(db_path)
    try:
        got = await again.get("durable")
        assert got is not None
        assert got.model_dump() == state.model_dump()
    finally:
        await again.close()


async def test_close_removes_owned_tempdir(state: FormState) -> None:
    settings = _make_settings()
    store = make_session_store(settings)
    sqlite_store = store
    assert isinstance(sqlite_store, SqliteSessionStore)
    tempdir = sqlite_store._owns_tempdir  # type: ignore[attr-defined]
    assert tempdir is not None
    assert tempdir.exists()
    # `make_session_store` is the production path that creates the db file via
    # `os.open(O_EXCL | 0o600)`; assert the artifact landed with the expected
    # POSIX mode rather than relying on the in-test helper alone.
    db_path = sqlite_store._db_path  # type: ignore[attr-defined]
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
    await sqlite_store.put("sid-1", state)
    await sqlite_store.close()
    assert not tempdir.exists()


def test_db_file_created_with_0600_permissions(tmp_path: Path) -> None:
    db_path = _create_db_file(tmp_path)
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600


def test_make_session_store_rejects_unwritable_path(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_mkdtemp(*_a: object, **_k: object) -> str:
        # Point at a path that already exists as a non-directory so the file
        # creation fails reliably.
        return "/dev/null/not-a-dir"

    monkeypatch.setattr("kestrel.mock_site.state.store.tempfile.mkdtemp", fake_mkdtemp)
    with pytest.raises(StoreInitError):
        make_session_store(_make_settings())


def test_factory_returns_sqlite_for_hard_memory_for_others() -> None:
    from kestrel.mock_site.state.memory import InMemorySessionStore

    hard = make_session_store(_make_settings(Difficulty.HARD))
    assert isinstance(hard, SqliteSessionStore)
    # Hard store creates a real tempdir; clean up.
    import asyncio

    asyncio.run(hard.close())

    easy = make_session_store(_make_settings(Difficulty.EASY))
    assert isinstance(easy, InMemorySessionStore)
    medium = make_session_store(_make_settings(Difficulty.MEDIUM))
    assert isinstance(medium, InMemorySessionStore)
