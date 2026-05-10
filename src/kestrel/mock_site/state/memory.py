"""In-memory session store. Used for EASY and MEDIUM difficulties."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from kestrel.mock_site.state.models import FormState


class InMemorySessionStore:
    """asyncio.Lock-guarded `dict[sid, (FormState, datetime_utc)]`."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[FormState, datetime]] = {}
        self._lock = asyncio.Lock()

    async def get(self, sid: str) -> FormState | None:
        async with self._lock:
            entry = self._data.get(sid)
        return entry[0] if entry is not None else None

    async def put(self, sid: str, state: FormState) -> None:
        now = datetime.now(UTC)
        async with self._lock:
            self._data[sid] = (state, now)

    async def delete(self, sid: str) -> None:
        async with self._lock:
            self._data.pop(sid, None)

    async def gc(self, older_than: timedelta) -> int:
        cutoff = datetime.now(UTC) - older_than
        async with self._lock:
            stale = [sid for sid, (_state, ts) in self._data.items() if ts < cutoff]
            for sid in stale:
                del self._data[sid]
        return len(stale)

    async def close(self) -> None:
        # Memory backend owns no resources; close is idempotent.
        return None


__all__ = ["InMemorySessionStore"]
