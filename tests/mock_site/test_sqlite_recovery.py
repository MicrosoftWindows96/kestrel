"""Recovery-path tests for `SqliteSessionStore`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kestrel.mock_site.state.models import FormState, VehicleStep
from kestrel.mock_site.state.sqlite import SqliteSessionStore
from kestrel.mock_site.state.store import (
    DEFAULT_SQLITE_FILENAME,
    StoreCorruptError,
)


def _create_db_file(tmp_path: Path) -> Path:
    db_path = tmp_path / DEFAULT_SQLITE_FILENAME
    fd = os.open(str(db_path), os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    return db_path


async def test_corrupt_payload_raises_store_corrupt_error(tmp_path: Path) -> None:
    db_path = _create_db_file(tmp_path)
    store = SqliteSessionStore(db_path)
    try:
        # Seed a valid row, then overwrite the payload with garbage bytes.
        await store.put("sid-1", FormState(vehicle=VehicleStep(vehicle_make="X")))
        conn = await store._connection()  # type: ignore[attr-defined]
        await conn.execute(
            "UPDATE sessions SET payload = ? WHERE sid = ?",
            (b"\x00\x01\x02 not-json", "sid-1"),
        )
        await conn.commit()
        with pytest.raises(StoreCorruptError):
            await store.get("sid-1")
    finally:
        await store.close()


async def test_corrupt_pydantic_payload_raises_store_corrupt_error(tmp_path: Path) -> None:
    db_path = _create_db_file(tmp_path)
    store = SqliteSessionStore(db_path)
    try:
        await store.put("sid-1", FormState())
        conn = await store._connection()  # type: ignore[attr-defined]
        # Valid JSON, invalid pydantic shape (extra forbidden key on FormState).
        await conn.execute(
            "UPDATE sessions SET payload = ? WHERE sid = ?",
            (b'{"not_a_step": {"x": 1}}', "sid-1"),
        )
        await conn.commit()
        with pytest.raises(StoreCorruptError):
            await store.get("sid-1")
    finally:
        await store.close()
