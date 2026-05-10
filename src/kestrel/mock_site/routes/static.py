"""Static asset mount.

Section 02 vendors real htmx 2.0.4 plus its SHA-256 hash and `LICENSE.htmx`.
This split only needs the directory to exist with placeholder files so the
mount registration succeeds and the no-egress test path can render.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

STATIC_DIR: Path = Path(__file__).resolve().parent.parent / "static"


def mount_static(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
