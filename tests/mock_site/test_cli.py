"""Tests for the mock-site command-line surface."""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from kestrel.mock_site import cli as cli_module


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip KESTREL_MOCK_* env vars so CLI tests start from defaults.

    monkeypatch's own teardown reverses each setenv/delenv automatically; the
    fixture body therefore performs setup only and returns implicitly.
    """
    for key in list(os.environ):
        if key.startswith("KESTREL_MOCK_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KESTREL_MOCK_SECRET", "test" * 8)
    monkeypatch.setenv("KESTREL_MOCK_QUIET", "1")


def test_help_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(cli_module.cli, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output.lower()


def test_invalid_difficulty_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_module, "uvicorn", _NoServeUvicorn())
    result = runner.invoke(cli_module.cli, ["serve", "--difficulty", "INVALID"])
    assert result.exit_code != 0


def test_invalid_insurer_exits_nonzero(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "uvicorn", _NoServeUvicorn())
    result = runner.invoke(cli_module.cli, ["serve", "--insurer", "INVALID"])
    assert result.exit_code != 0


def test_reload_flag_rejected(runner: CliRunner) -> None:
    result = runner.invoke(cli_module.cli, ["serve", "--reload"])
    assert result.exit_code != 0


def test_posix_only_check_fires(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(cli_module, "uvicorn", _NoServeUvicorn())
    result = runner.invoke(cli_module.cli, ["serve"])
    assert result.exit_code == 2
    assert "POSIX-only platform required" in result.output


def test_subcommandless_invocation(runner: CliRunner) -> None:
    result = runner.invoke(cli_module.cli, [])
    # Per typer convention (Click 8.2+), `no_args_is_help` triggers help with
    # exit 2 (missing command). Either 0 or 2 is acceptable; uvicorn must not run.
    assert result.exit_code in {0, 2}
    assert "serve" in result.output.lower()


def test_env_difficulty_applied(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("KESTREL_MOCK_DIFFICULTY", "hard")
    monkeypatch.setattr(cli_module, "uvicorn", _CapturingUvicorn(captured))
    result = runner.invoke(cli_module.cli, ["serve"])
    assert result.exit_code == 0, result.output + result.output
    app = captured["app"]
    assert app.state.settings.difficulty.value == "hard"


def test_cli_wins_over_env(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("KESTREL_MOCK_DIFFICULTY", "easy")
    monkeypatch.setattr(cli_module, "uvicorn", _CapturingUvicorn(captured))
    result = runner.invoke(cli_module.cli, ["serve", "--difficulty", "hard"])
    assert result.exit_code == 0, result.output + result.output
    app = captured["app"]
    assert app.state.settings.difficulty.value == "hard"


class _NoServeUvicorn:
    """Stand-in for the `uvicorn` module that refuses to actually serve."""

    @staticmethod
    def run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("uvicorn.run should not be reached when CLI rejects input")


class _CapturingUvicorn:
    def __init__(self, captured: dict[str, object]) -> None:
        self._captured = captured

    def run(self, app: object, **kwargs: object) -> None:
        self._captured["app"] = app
        self._captured["kwargs"] = kwargs
