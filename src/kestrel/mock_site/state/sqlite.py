"""SQLite-backed session store. Used for HARD difficulty.

Schema (single table):
    sessions(sid TEXT PRIMARY KEY, payload BLOB NOT NULL, updated_at REAL NOT NULL)

`payload` is utf-8 JSON of `FormState.model_dump(mode='json', exclude_none=True)`.
`updated_at` is unix-seconds (REAL) for trivial gc comparisons.

Atomic file creation (security-relevant): the database file is created
upstream in `make_session_store` via
`os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)` so the path
exists with mode 0o600 before aiosqlite opens its connection. This
eliminates a TOCTOU race where another process could race the open and
sets POSIX permissions before any writes land.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite
import structlog
from pydantic import ValidationError

from kestrel.mock_site.state.models import FormState
from kestrel.mock_site.state.store import (
    StoreCorruptError,
    StoreLockedError,
)

_LOCKED_MESSAGE = "database is locked"
_BUSY_TIMEOUT_MS = 5000
_logger = structlog.get_logger("kestrel.mock_site.state")


class SqliteSessionStore:
    """aiosqlite-backed store; one connection per process; WAL journal."""

    def __init__(self, db_path: Path, *, owns_tempdir: Path | None = None) -> None:
        self._db_path = db_path
        self._owns_tempdir = owns_tempdir
        self._conn: aiosqlite.Connection | None = None
        self._init_lock = asyncio.Lock()

    async def _connection(self) -> aiosqlite.Connection:
        cached = self._conn
        if cached is not None:
            return cached
        async with self._init_lock:
            # Defensive double-check: another coroutine may have raced past
            # the outer guard and finished init while we waited on the lock.
            cached = self._conn
            if cached is not None:
                return cached
            try:
                conn = await aiosqlite.connect(str(self._db_path))
                await conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        sid TEXT PRIMARY KEY,
                        payload BLOB NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                await conn.commit()
            except sqlite3.OperationalError as exc:
                if _LOCKED_MESSAGE in str(exc):
                    raise StoreLockedError(str(exc)) from exc
                raise
            self._conn = conn
            return conn

    async def get(self, sid: str) -> FormState | None:
        conn = await self._connection()
        try:
            async with conn.execute("SELECT payload FROM sessions WHERE sid = ?", (sid,)) as cursor:
                row = await cursor.fetchone()
        except sqlite3.OperationalError as exc:
            if _LOCKED_MESSAGE in str(exc):
                raise StoreLockedError(str(exc)) from exc
            raise
        if row is None:
            return None
        payload_bytes = row[0]
        try:
            decoded = json.loads(payload_bytes)
            return FormState.model_validate(decoded)
        except (json.JSONDecodeError, ValidationError) as exc:
            _logger.warning("state_corrupt", session_id=sid)
            raise StoreCorruptError(f"corrupt payload for sid={sid}") from exc

    async def put(self, sid: str, state: FormState) -> None:
        conn = await self._connection()
        payload = json.dumps(
            state.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        updated_at = datetime.now(UTC).timestamp()
        try:
            await conn.execute(
                "INSERT INTO sessions (sid, payload, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(sid) DO UPDATE SET payload=excluded.payload, "
                "updated_at=excluded.updated_at",
                (sid, payload, updated_at),
            )
            await conn.commit()
        except sqlite3.OperationalError as exc:
            if _LOCKED_MESSAGE in str(exc):
                raise StoreLockedError(str(exc)) from exc
            raise

    async def delete(self, sid: str) -> None:
        conn = await self._connection()
        try:
            await conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
            await conn.commit()
        except sqlite3.OperationalError as exc:
            if _LOCKED_MESSAGE in str(exc):
                raise StoreLockedError(str(exc)) from exc
            raise

    async def gc(self, older_than: timedelta) -> int:
        conn = await self._connection()
        cutoff = (datetime.now(UTC) - older_than).timestamp()
        try:
            cursor = await conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
            removed = cursor.rowcount or 0
            await conn.commit()
        except sqlite3.OperationalError as exc:
            if _LOCKED_MESSAGE in str(exc):
                raise StoreLockedError(str(exc)) from exc
            raise
        return int(removed)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        if self._owns_tempdir is not None:
            shutil.rmtree(self._owns_tempdir, ignore_errors=True)


__all__ = ["SqliteSessionStore"]
