"""FastAPI app factory.

Per plan section 9: build a fully wired FastAPI app for the given
Settings. All `app.state.*` slots are populated synchronously BEFORE
return. The session store is built per difficulty (memory for EASY /
MEDIUM, sqlite for HARD) and the lifespan handler owns the janitor
task lifecycle. PersonaSpec and CsrfService remain stub placeholders;
sections 09/10 and 08 replace each with the real builder.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from kestrel.mock_site.config import Difficulty, Persona, Settings
from kestrel.mock_site.logging import configure_logging
from kestrel.mock_site.middleware.request_logger import RequestLoggerMiddleware
from kestrel.mock_site.routes import health, quote
from kestrel.mock_site.routes.static import mount_static
from kestrel.mock_site.state import SessionStore, make_session_store, run_janitor

INTERMITTENT_PROB_LOW = 0.10
INTERMITTENT_PROB_HIGH = 0.30


@dataclass(frozen=True, slots=True)
class PersonaSpecStub:
    """Phase A placeholder. Section 09/10 replace with real PersonaSpec."""

    name: Persona
    template_dir: str

    def __repr__(self) -> str:
        return f"<PersonaSpec name={self.name}>"


@dataclass(frozen=True, slots=True)
class CsrfServiceStub:
    """Phase A placeholder. Section 08 replaces with real CsrfService."""

    enabled: bool

    def __repr__(self) -> str:
        return f"<CsrfServiceStub enabled={self.enabled}>"


def create_app(settings: Settings) -> FastAPI:
    persona_spec = _build_persona_spec(settings)
    session_store = make_session_store(settings)
    csrf_service = _build_csrf_service(settings)
    intermittent_prob = _draw_intermittent_prob(settings.seed)

    configure_logging(
        quiet=settings.quiet,
        log_file=settings.log_file,
        json_renderer=True,
    )

    app = FastAPI(
        title="kestrel mock site",
        version="0.1.0",
        lifespan=_make_lifespan(session_store, settings.janitor_interval_seconds),
    )
    app.state.settings = settings
    app.state.persona_spec = persona_spec
    app.state.session_store = session_store
    app.state.csrf_service = csrf_service
    app.state.intermittent_challenge_prob = intermittent_prob
    app.state.templates = _build_templates(settings)

    mount_static(app)
    _register_middleware(app)
    _register_routers(app)
    return app


def _build_persona_spec(settings: Settings) -> PersonaSpecStub:
    return PersonaSpecStub(name=settings.persona, template_dir=settings.persona.value)


def _build_csrf_service(settings: Settings) -> CsrfServiceStub:
    return CsrfServiceStub(enabled=settings.difficulty is Difficulty.HARD)


def _draw_intermittent_prob(seed: int) -> float:
    # Non-cryptographic by design: the prob must be reproducible across factory
    # calls with the same seed so HARD-mode tests are deterministic.
    rng = random.Random(seed)  # noqa: S311
    return rng.uniform(INTERMITTENT_PROB_LOW, INTERMITTENT_PROB_HIGH)


def _build_templates(settings: Settings) -> Jinja2Templates:
    """Return a Jinja2Templates rooted at the active persona's directory."""
    template_root = Path(__file__).resolve().parent / "templates"
    persona_dir = template_root / settings.persona.value
    if settings.persona is Persona.C and settings.difficulty is Difficulty.EASY:
        directories = [str(persona_dir / "easy"), str(persona_dir)]
    else:
        directories = [str(persona_dir)]
    return Jinja2Templates(directory=directories)


def _register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggerMiddleware)


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(quote.router)


def _make_lifespan(store: SessionStore, interval_seconds: float) -> Callable[[FastAPI], Any]:
    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(run_janitor(store, interval_seconds))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await store.close()
            logging.shutdown()

    return _lifespan
