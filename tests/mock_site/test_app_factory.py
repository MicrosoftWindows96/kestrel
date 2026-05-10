"""Tests for `create_app` factory."""

from __future__ import annotations

from fastapi import FastAPI

from kestrel.mock_site import logging as mock_logging
from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Difficulty, Persona, Settings

REPR_FIELDS = ("settings", "persona_spec", "session_store", "csrf_service")


def _settings(difficulty: Difficulty, persona: Persona, *, seed: int = 20260510) -> Settings:
    return Settings(
        difficulty=difficulty,
        persona=persona,
        host="127.0.0.1",
        port=8000,
        log_file=None,
        quiet=True,
        seed=seed,
        secret=b"test" * 8,
        janitor_interval_seconds=86400,
        intermittent_challenge_prob=0.10,
    )


def test_create_app_returns_fastapi_for_every_combo(
    difficulty: Difficulty, persona: Persona
) -> None:
    mock_logging.reset_for_tests()
    fastapi_app = create_app(_settings(difficulty, persona))
    assert isinstance(fastapi_app, FastAPI)


async def test_create_app_populates_state_synchronously(app: FastAPI) -> None:
    for slot in REPR_FIELDS:
        assert hasattr(app.state, slot), f"missing app.state.{slot}"
    assert hasattr(app.state, "intermittent_challenge_prob")


def test_intermittent_challenge_prob_in_range_and_stable(
    difficulty: Difficulty, persona: Persona
) -> None:
    mock_logging.reset_for_tests()
    settings_one = _settings(difficulty, persona, seed=20260510)
    app_one = create_app(settings_one)
    mock_logging.reset_for_tests()
    settings_two = _settings(difficulty, persona, seed=20260510)
    app_two = create_app(settings_two)
    prob_one = app_one.state.intermittent_challenge_prob
    prob_two = app_two.state.intermittent_challenge_prob
    assert 0.10 <= prob_one <= 0.30
    assert prob_one == prob_two


def test_create_app_idempotent(difficulty: Difficulty, persona: Persona) -> None:
    """Two factory calls with the same Settings do not double-configure structlog."""
    mock_logging.reset_for_tests()
    settings = _settings(difficulty, persona)
    create_app(settings)
    assert mock_logging.is_configured()
    create_app(settings)


def test_settings_repr_redacts_secret(difficulty: Difficulty, persona: Persona) -> None:
    settings = _settings(difficulty, persona)
    rendered = repr(settings)
    assert "testtest" not in rendered
    assert "secret" not in rendered.lower()
    assert "seed" not in rendered.lower()
