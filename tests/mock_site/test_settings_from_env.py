"""Tests for Settings.from_env_and_cli precedence and validation."""

from __future__ import annotations

import os

import pytest

from kestrel.mock_site.config import (
    DEFAULT_HOST,
    DEFAULT_JANITOR_INTERVAL_SECONDS,
    DEFAULT_PORT,
    Difficulty,
    Persona,
    Settings,
)

VALID_SECRET = b"test" * 8


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("KESTREL_MOCK_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KESTREL_MOCK_SECRET", VALID_SECRET.decode("ascii"))


def test_defaults_with_empty_env_and_no_cli() -> None:
    settings = Settings.from_env_and_cli({})
    assert settings.difficulty == Difficulty.EASY
    assert settings.persona == Persona.A
    assert settings.host == DEFAULT_HOST
    assert settings.port == DEFAULT_PORT
    assert settings.log_file is None
    assert settings.quiet is False
    assert settings.janitor_interval_seconds == DEFAULT_JANITOR_INTERVAL_SECONDS
    assert settings.secret == VALID_SECRET
    assert settings.intermittent_challenge_prob == 0.0


@pytest.mark.parametrize(
    ("env_key", "env_val", "attr", "expected"),
    [
        ("KESTREL_MOCK_DIFFICULTY", "hard", "difficulty", Difficulty.HARD),
        ("KESTREL_MOCK_INSURER", "persona_b", "persona", Persona.B),
        ("KESTREL_MOCK_HOST", "0.0.0.0", "host", "0.0.0.0"),  # noqa: S104
        ("KESTREL_MOCK_PORT", "12345", "port", 12345),
        ("KESTREL_MOCK_QUIET", "true", "quiet", True),
        ("KESTREL_MOCK_JANITOR_INTERVAL", "120", "janitor_interval_seconds", 120),
        ("KESTREL_MOCK_SEED", "424242", "seed", 424242),
    ],
)
def test_each_knob_env_only(
    monkeypatch: pytest.MonkeyPatch,
    env_key: str,
    env_val: str,
    attr: str,
    expected: object,
) -> None:
    monkeypatch.setenv(env_key, env_val)
    settings = Settings.from_env_and_cli({})
    assert getattr(settings, attr) == expected


@pytest.mark.parametrize(
    ("env_pair", "cli_pair", "attr", "expected"),
    [
        (
            ("KESTREL_MOCK_DIFFICULTY", "easy"),
            ("difficulty", "hard"),
            "difficulty",
            Difficulty.HARD,
        ),
        (
            ("KESTREL_MOCK_INSURER", "persona_a"),
            ("persona", "persona_c"),
            "persona",
            Persona.C,
        ),
        (("KESTREL_MOCK_PORT", "1234"), ("port", 5678), "port", 5678),
    ],
)
def test_each_knob_cli_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
    env_pair: tuple[str, str],
    cli_pair: tuple[str, object],
    attr: str,
    expected: object,
) -> None:
    monkeypatch.setenv(*env_pair)
    settings = Settings.from_env_and_cli({cli_pair[0]: cli_pair[1]})
    assert getattr(settings, attr) == expected


@pytest.mark.parametrize(
    ("env_key", "bad_val"),
    [
        ("KESTREL_MOCK_DIFFICULTY", "INVALID"),
        ("KESTREL_MOCK_INSURER", "persona_z"),
        ("KESTREL_MOCK_PORT", "70000"),
        ("KESTREL_MOCK_PORT", "0"),
        ("KESTREL_MOCK_QUIET", "MAYBE"),
        ("KESTREL_MOCK_JANITOR_INTERVAL", "0"),
    ],
)
def test_each_knob_bad_value_raises(
    monkeypatch: pytest.MonkeyPatch, env_key: str, bad_val: str
) -> None:
    monkeypatch.setenv(env_key, bad_val)
    with pytest.raises(ValueError, match=r"invalid|out of range|must be"):
        Settings.from_env_and_cli({})


def test_seed_default_random_in_cli_deterministic_in_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KESTREL_MOCK_SEED", raising=False)
    seeds = {Settings.from_env_and_cli({}).seed for _ in range(5)}
    # System random produces distinct values across calls (probabilistic; 63 bits).
    assert len(seeds) == 5
    for seed in seeds:
        assert isinstance(seed, int)


def test_unknown_cli_override_key_raises() -> None:
    with pytest.raises(ValueError, match=r"unknown override keys"):
        Settings.from_env_and_cli({"persona_typo": "persona_b"})


def test_secret_length_exactly_32_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KESTREL_MOCK_SECRET", "short")
    with pytest.raises(ValueError, match=r"must be exactly"):
        Settings.from_env_and_cli({})
    monkeypatch.setenv("KESTREL_MOCK_SECRET", "x" * 33)
    with pytest.raises(ValueError, match=r"must be exactly"):
        Settings.from_env_and_cli({})
    monkeypatch.setenv("KESTREL_MOCK_SECRET", "x" * 32)
    settings = Settings.from_env_and_cli({})
    assert len(settings.secret) == 32


def test_intermittent_prob_not_user_settable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KESTREL_MOCK_INTERMITTENT_CHALLENGE_PROB", "0.5")
    settings = Settings.from_env_and_cli({})
    assert settings.intermittent_challenge_prob == 0.0
