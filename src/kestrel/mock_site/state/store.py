"""SessionStore Protocol, typed errors, and backend factory.

EASY and MEDIUM difficulties run an in-memory store; HARD runs the
SQLite-backed store so `test_sqlite_recovery` exercises real failure
paths (locked db, corrupt row).
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Final, Protocol

from fastapi import Request

from kestrel.mock_site.config import Difficulty, Settings
from kestrel.mock_site.state.models import FormState

DEFAULT_SQLITE_DIR_PREFIX: Final[str] = "kestrel-mock-"
DEFAULT_SQLITE_FILENAME: Final[str] = "sessions.sqlite"


class StoreError(Exception):
    """Base for all session-store errors."""


class StoreInitError(StoreError):
    """Backend failed to initialize (e.g., missing or unwritable tempdir)."""


class StoreLockedError(StoreError):
    """SQLite database is locked; transient."""


class StoreCorruptError(StoreError):
    """Stored row failed to deserialize; not transient."""


class SessionStore(Protocol):
    async def get(self, sid: str) -> FormState | None: ...
    async def put(self, sid: str, state: FormState) -> None: ...
    async def delete(self, sid: str) -> None: ...
    async def gc(self, older_than: timedelta) -> int: ...
    async def close(self) -> None: ...


def make_session_store(settings: Settings) -> SessionStore:
    """Return the appropriate backend for the active difficulty."""
    if settings.difficulty is Difficulty.HARD:
        return _build_sqlite_store()
    # Local import keeps the module free of FastAPI / aiosqlite cycles when
    # only the Protocol is needed.
    from kestrel.mock_site.state.memory import InMemorySessionStore

    return InMemorySessionStore()


def _build_sqlite_store() -> SessionStore:
    from kestrel.mock_site.state.sqlite import SqliteSessionStore

    tempdir = Path(tempfile.mkdtemp(prefix=f"{DEFAULT_SQLITE_DIR_PREFIX}{os.getpid()}-"))
    db_path = tempdir / DEFAULT_SQLITE_FILENAME
    try:
        fd = os.open(str(db_path), os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    except OSError as exc:
        shutil.rmtree(tempdir, ignore_errors=True)
        raise StoreInitError(f"failed to create sqlite db at {db_path}: {exc}") from exc
    atexit.register(shutil.rmtree, str(tempdir), True)
    return SqliteSessionStore(db_path, owns_tempdir=tempdir)


def get_session_store(request: Request) -> SessionStore:
    """FastAPI dependency: per-request handle to the active store."""
    store: SessionStore = request.app.state.session_store
    return store


__all__ = [
    "DEFAULT_SQLITE_DIR_PREFIX",
    "DEFAULT_SQLITE_FILENAME",
    "SessionStore",
    "StoreCorruptError",
    "StoreError",
    "StoreInitError",
    "StoreLockedError",
    "get_session_store",
    "make_session_store",
]
