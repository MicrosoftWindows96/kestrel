"""Mock-site command-line entry point.

Boot sequence per plan section 8: POSIX guard, env+CLI parse into
Settings, structlog configure, build app, hand off to uvicorn. The
`--reload` flag is intentionally absent; the public surface forbids
it because reload spawns a child process and our no-egress invariant
must hold for the same process tree the test fixture asserts on.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn

from kestrel.mock_site.app import create_app
from kestrel.mock_site.config import Settings
from kestrel.mock_site.logging import configure_logging

cli = typer.Typer(no_args_is_help=True, add_completion=False, name="mock-site")


@cli.callback()
def _root() -> None:
    """Mock UK insurance quote site for kestrel adapter testing."""


@cli.command()
def serve(
    difficulty: Annotated[
        str | None,
        typer.Option("--difficulty", help="easy | medium | hard"),
    ] = None,
    insurer: Annotated[
        str | None,
        typer.Option("--insurer", help="persona_a | persona_b | persona_c"),
    ] = None,
    host: Annotated[
        str | None,
        typer.Option("--host", help="bind host; defaults to 127.0.0.1"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", help="bind port; defaults to 8000"),
    ] = None,
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", help="rotating-file sink (10 MB x 3)"),
    ] = None,
    quiet: Annotated[
        bool | None,
        typer.Option("--quiet/--no-quiet", help="silence request events"),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", help="random seed; system-random when omitted"),
    ] = None,
) -> None:
    """Run the mock site."""
    _enforce_posix()
    cli_overrides = _collect_overrides(
        difficulty=difficulty,
        insurer=insurer,
        host=host,
        port=port,
        log_file=log_file,
        quiet=quiet,
        seed=seed,
    )
    try:
        settings = Settings.from_env_and_cli(cli_overrides)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    configure_logging(
        quiet=settings.quiet,
        log_file=settings.log_file,
        json_renderer=None,
    )
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=False,
        workers=1,
        log_config=None,
    )


def _enforce_posix() -> None:
    if platform.system() not in {"Linux", "Darwin"}:
        typer.echo("POSIX-only platform required", err=True)
        raise typer.Exit(2)


def _collect_overrides(
    *,
    difficulty: str | None,
    insurer: str | None,
    host: str | None,
    port: int | None,
    log_file: Path | None,
    quiet: bool | None,
    seed: int | None,
) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if difficulty is not None:
        overrides["difficulty"] = difficulty
    if insurer is not None:
        overrides["persona"] = insurer
    if host is not None:
        overrides["host"] = host
    if port is not None:
        overrides["port"] = port
    if log_file is not None:
        overrides["log_file"] = log_file
    if quiet is not None:
        overrides["quiet"] = quiet
    if seed is not None:
        overrides["seed"] = seed
    return overrides


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
