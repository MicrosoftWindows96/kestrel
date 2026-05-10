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
from kestrel.mock_site.csrf import CsrfService
from kestrel.mock_site.logging import configure_logging
from kestrel.mock_site.middleware.challenge import ChallengeMiddleware
from kestrel.mock_site.middleware.latency import LatencyMiddleware
from kestrel.mock_site.middleware.request_logger import RequestLoggerMiddleware
from kestrel.mock_site.routes import challenge, health, quote
from kestrel.mock_site.routes.static import mount_static
from kestrel.mock_site.state import SessionStore, make_session_store, run_janitor

INTERMITTENT_PROB_LOW = 0.10
INTERMITTENT_PROB_HIGH = 0.30


_PERSONA_PREMIUM_OFFSETS: dict[Persona, int] = {
    Persona.A: 0,
    Persona.B: 175,
    Persona.C: 350,
}

_PERSONA_ADDON_CATALOGS: dict[Persona, tuple[str, ...]] = {
    Persona.A: ("breakdown", "legal_cover", "courtesy_car", "key_cover", "windscreen"),
    Persona.B: ("breakdown", "legal_cover", "windscreen"),
    Persona.C: ("breakdown", "courtesy_car", "key_cover"),
}


@dataclass(frozen=True, slots=True)
class PersonaSpecStub:
    """Phase A placeholder. Sections 09/10 replace with the full PersonaSpec.

    Carries the subset of fields that the active route surface
    (sections 06-08) reads. The full divergence-axis matrix lands when
    persona_b and persona_c content arrives.
    """

    name: Persona
    template_dir: str
    premium_seed_offset: int
    addon_catalog: tuple[str, ...]

    def __repr__(self) -> str:
        return f"<PersonaSpec name={self.name}>"


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
    _register_middleware(app, settings)
    _register_routers(app)
    return app


def _build_persona_spec(settings: Settings) -> PersonaSpecStub:
    return PersonaSpecStub(
        name=settings.persona,
        template_dir=settings.persona.value,
        premium_seed_offset=_PERSONA_PREMIUM_OFFSETS[settings.persona],
        addon_catalog=_PERSONA_ADDON_CATALOGS[settings.persona],
    )


def _build_csrf_service(settings: Settings) -> CsrfService:
    return CsrfService(secret=settings.secret)


def _draw_intermittent_prob(seed: int) -> float:
    # Non-cryptographic by design: the prob must be reproducible across factory
    # calls with the same seed so HARD-mode tests are deterministic.
    rng = random.Random(seed)  # noqa: S311
    return rng.uniform(INTERMITTENT_PROB_LOW, INTERMITTENT_PROB_HIGH)


def _build_templates(settings: Settings) -> Jinja2Templates:
    """Return a Jinja2Templates with the persona-aware search path.

    Search order: persona dir (and the persona/easy/ overlay for persona_c
    + EASY) first, then the shared templates root so that `base.html` and
    other persona-agnostic helpers resolve.
    """
    template_root = Path(__file__).resolve().parent / "templates"
    persona_dir = template_root / settings.persona.value
    directories: list[str] = []
    if settings.persona is Persona.C and settings.difficulty is Difficulty.EASY:
        directories.append(str(persona_dir / "easy"))
    directories.append(str(persona_dir))
    directories.append(str(template_root))
    return Jinja2Templates(directory=directories)


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    # Starlette wraps middlewares in reverse-registration order, so the
    # last `add_middleware` call is the outermost layer at request time.
    # Section 11 keeps RequestLoggerMiddleware as the outermost layer so
    # it observes status, duration, and request_id for every leg.
    app.add_middleware(ChallengeMiddleware)
    app.add_middleware(LatencyMiddleware, settings=settings)
    app.add_middleware(RequestLoggerMiddleware)


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(quote.router)
    app.include_router(challenge.router)


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
