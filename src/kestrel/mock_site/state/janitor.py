"""Async janitor task. Periodically GCs stale sessions.

Behaviour contract (locked by tests):
- Sleeps `interval_seconds` BEFORE the first tick.
- Each tick calls `await store.gc(_GC_AGE)`. Generic exceptions are logged
  at WARNING and swallowed; only `asyncio.CancelledError` breaks the loop.
- On cancellation: emits `janitor_cancelled` then re-raises so the
  enclosing lifespan handler can complete its teardown.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Final

import structlog

from kestrel.mock_site.state.store import SessionStore

_GC_AGE: Final[timedelta] = timedelta(minutes=30)
_logger = structlog.get_logger("kestrel.mock_site.state.janitor")


async def run_janitor(store: SessionStore, interval_seconds: float) -> None:
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await store.gc(_GC_AGE)
            except Exception as exc:
                _logger.warning(
                    "janitor_gc_failed",
                    error=type(exc).__name__,
                    detail=str(exc),
                )
    except asyncio.CancelledError:
        _logger.info("janitor_cancelled")
        raise


__all__ = ["run_janitor"]
