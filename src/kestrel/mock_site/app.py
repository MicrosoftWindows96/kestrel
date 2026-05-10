"""FastAPI app factory.

Per plan section 9: build a fully wired FastAPI app for the given
Settings. All `app.state.*` slots are populated synchronously BEFORE
return (Pass 3 U1). Phase A populates persona_spec, session_store, and
csrf_service as placeholder stubs; sections 04, 05, and 08 replace each
with the real builder. Tests assert presence and type-shape only.
"""

from __future__ import annotations

import logging
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from kestrel.mock_site.config import Persona, Settings
from kestrel.mock_site.logging import configure_logging
from kestrel.mock_site.middleware.request_logger import RequestLoggerMiddleware
from kestrel.mock_site.routes import health
from kestrel.mock_site.routes.static import mount_static

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
class SessionStoreStub:
    """Phase A placeholder. Section 05 replaces with real SessionStore."""

    backend: str

    def __repr__(self) -> str:
        return f"<SessionStoreStub backend={self.backend}>"


@dataclass(frozen=True, slots=True)
class CsrfServiceStub:
    """Phase A placeholder. Section 08 replaces with real CsrfService."""

    enabled: bool

    def __repr__(self) -> str:
        return f"<CsrfServiceStub enabled={self.enabled}>"


def create_app(settings: Settings) -> FastAPI:
    """Build the mock-site FastAPI app.

    The factory is idempotent at the structlog layer: repeat calls with
    the same Settings reuse the existing logger config. Each call
    produces a fresh FastAPI instance.
    """
    persona_spec = _build_persona_spec(settings)
    session_store = _build_session_store(settings)
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
        lifespan=_make_lifespan(),
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


def _build_session_store(settings: Settings) -> SessionStoreStub:
    backend = "sqlite" if settings.difficulty.value == "hard" else "memory"
    return SessionStoreStub(backend=backend)


def _build_csrf_service(settings: Settings) -> CsrfServiceStub:
    return CsrfServiceStub(enabled=settings.difficulty.value == "hard")


def _draw_intermittent_prob(seed: int) -> float:
    # Non-cryptographic by design: the prob must be reproducible across factory
    # calls with the same seed so HARD-mode tests are deterministic.
    rng = random.Random(seed)  # noqa: S311
    return rng.uniform(INTERMITTENT_PROB_LOW, INTERMITTENT_PROB_HIGH)


def _build_templates(_settings: Settings) -> Jinja2Templates:
    """Return a Jinja2Templates rooted at the package templates dir.

    The directory tree is part of the source distribution (committed
    placeholders per persona). Section 02 vendors persona-specific
    templates beneath this root. The factory does NOT mkdir at runtime
    because the package install location may be read-only.
    """
    template_root = Path(__file__).resolve().parent / "templates"
    return Jinja2Templates(directory=str(template_root))


def _register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggerMiddleware)


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)


def _make_lifespan() -> Any:
    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            logging.shutdown()

    return _lifespan
