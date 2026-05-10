"""Mock-site configuration types and env+CLI precedence resolver.

Pinned by plan section 6 (core types) and section 7 (configuration surface).

`Settings` is frozen and slotted; all knobs are typed and validated.
The `KESTREL_MOCK_*` env namespace is reserved for this split; the kestrel
core never reads it.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

DEFAULT_PORT: Final[int] = 8000
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_JANITOR_INTERVAL_SECONDS: Final[int] = 60
SECRET_LENGTH_BYTES: Final[int] = 32
ENV_PREFIX: Final[str] = "KESTREL_MOCK_"

_TRUE_TOKENS: Final[frozenset[str]] = frozenset({"1", "true"})
_FALSE_TOKENS: Final[frozenset[str]] = frozenset({"0", "false"})

ACCEPTED_OVERRIDE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "difficulty",
        "persona",
        "host",
        "port",
        "log_file",
        "quiet",
        "seed",
        "janitor_interval_seconds",
    }
)


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Persona(StrEnum):
    A = "persona_a"
    B = "persona_b"
    C = "persona_c"


class FieldIdStrategy(StrEnum):
    STABLE = "stable"
    DATA_TEST_ONLY = "data_test_only"
    RANDOM_SUFFIX = "random_suffix"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class Settings:
    """Mock-site runtime settings.

    `intermittent_challenge_prob` is NOT user-settable. It is drawn from
    `random.Random(seed).uniform(0.10, 0.30)` at create_app time. It
    appears here for pass-through to test fixtures and for type-shape
    consistency, but env/CLI loaders set it to 0.0 and the app factory
    overrides it.
    """

    difficulty: Difficulty
    persona: Persona
    host: str
    port: int
    log_file: Path | None
    quiet: bool
    seed: int
    secret: bytes
    janitor_interval_seconds: int
    intermittent_challenge_prob: float

    def __repr__(self) -> str:
        return f"<Settings difficulty={self.difficulty} persona={self.persona} ...>"

    def __post_init__(self) -> None:
        _validate_settings(self)

    @classmethod
    def from_env_and_cli(cls, cli_overrides: Mapping[str, Any]) -> Settings:
        """Build Settings from env vars + CLI overrides.

        Precedence (highest first): CLI > env > default. Bad values raise
        ValueError; the CLI surface converts those to a non-zero typer exit.
        Unknown keys in `cli_overrides` raise ValueError so caller typos
        cannot silently fall back to defaults.
        """
        unknown = set(cli_overrides) - ACCEPTED_OVERRIDE_KEYS
        if unknown:
            raise ValueError(f"unknown override keys: {sorted(unknown)}")
        env = os.environ
        difficulty = _coerce_enum(Difficulty, _pick("difficulty", cli_overrides, env, "easy"))
        persona = _coerce_enum(
            Persona, _pick("persona", cli_overrides, env, "persona_a", env_key="INSURER")
        )
        host = _pick("host", cli_overrides, env, DEFAULT_HOST)
        port = _coerce_int(_pick("port", cli_overrides, env, str(DEFAULT_PORT)))
        log_file_raw = _pick("log_file", cli_overrides, env, None)
        log_file = Path(log_file_raw) if log_file_raw else None
        quiet = _coerce_bool(_pick("quiet", cli_overrides, env, "false"))
        seed = _resolve_seed(cli_overrides, env)
        secret = _resolve_secret(env)
        janitor_interval_seconds = _coerce_int(
            _pick(
                "janitor_interval_seconds",
                cli_overrides,
                env,
                str(DEFAULT_JANITOR_INTERVAL_SECONDS),
                env_key="JANITOR_INTERVAL",
            )
        )
        return cls(
            difficulty=difficulty,
            persona=persona,
            host=host,
            port=port,
            log_file=log_file,
            quiet=quiet,
            seed=seed,
            secret=secret,
            janitor_interval_seconds=janitor_interval_seconds,
            intermittent_challenge_prob=0.0,
        )

    def with_intermittent_challenge_prob(self, prob: float) -> Settings:
        """Return a new Settings with the drawn intermittent challenge prob."""
        return replace(self, intermittent_challenge_prob=prob)


def _validate_settings(settings: Settings) -> None:
    if not isinstance(settings.difficulty, Difficulty):
        raise TypeError(f"difficulty must be Difficulty enum; got {type(settings.difficulty)!r}")
    if not isinstance(settings.persona, Persona):
        raise TypeError(f"persona must be Persona enum; got {type(settings.persona)!r}")
    if not isinstance(settings.secret, bytes):
        raise TypeError(f"secret must be bytes; got {type(settings.secret)!r}")
    if not 1 <= settings.port <= 65535:
        raise ValueError(f"port out of range: {settings.port}")
    if len(settings.secret) != SECRET_LENGTH_BYTES:
        raise ValueError(
            f"secret must be exactly {SECRET_LENGTH_BYTES} bytes; got {len(settings.secret)}"
        )
    if settings.janitor_interval_seconds <= 0:
        raise ValueError(
            f"janitor_interval_seconds must be > 0; got {settings.janitor_interval_seconds}"
        )
    if not 0.0 <= settings.intermittent_challenge_prob <= 1.0:
        raise ValueError(
            "intermittent_challenge_prob must be in [0.0, 1.0]; got "
            f"{settings.intermittent_challenge_prob}"
        )


def _pick(
    key: str,
    cli: Mapping[str, Any],
    env: Mapping[str, str],
    default: Any,
    *,
    env_key: str | None = None,
) -> Any:
    if key in cli and cli[key] is not None:
        return cli[key]
    env_var = ENV_PREFIX + (env_key or key.upper())
    if env_var in env:
        return env[env_var]
    return default


def _coerce_enum(enum_cls: type[StrEnum], raw: Any) -> Any:
    if isinstance(raw, enum_cls):
        return raw
    try:
        return enum_cls(str(raw))
    except ValueError as exc:
        raise ValueError(
            f"invalid {enum_cls.__name__}: {raw!r}; valid: {[e.value for e in enum_cls]}"
        ) from exc


def _coerce_int(raw: Any) -> int:
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    try:
        return int(str(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer value: {raw!r}") from exc


def _coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    token = str(raw).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    raise ValueError(f"invalid boolean value: {raw!r}; expected one of 1/true/0/false")


def _resolve_seed(cli: Mapping[str, Any], env: Mapping[str, str]) -> int:
    raw = _pick("seed", cli, env, None)
    if raw is None:
        return secrets.randbits(63)
    return _coerce_int(raw)


def _resolve_secret(env: Mapping[str, str]) -> bytes:
    raw = env.get(ENV_PREFIX + "SECRET")
    if raw is None:
        return secrets.token_bytes(SECRET_LENGTH_BYTES)
    encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(encoded) != SECRET_LENGTH_BYTES:
        raise ValueError(
            f"{ENV_PREFIX}SECRET must be exactly {SECRET_LENGTH_BYTES} bytes; got {len(encoded)}"
        )
    return encoded
