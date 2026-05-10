"""Liveness and readiness probes.

Both return 200 with `{"status": "ok"}`. Skipped by RequestLoggerMiddleware
so health checks do not pollute logs. `/readyz` will probe the session
store starting in section 05; in this split it is a thin alias of
`/healthz` because the store is a placeholder.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, str]:
    return {"status": "ok"}
