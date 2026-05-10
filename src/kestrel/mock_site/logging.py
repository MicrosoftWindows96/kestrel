"""structlog one-shot configuration with stdlib bridge.

Per plan section 16: configure ONCE; module-level; idempotent. structlog
events are routed through the stdlib root logger via
`structlog.stdlib.LoggerFactory` so that `RotatingFileHandler` (when
`--log-file` is set) and the default stderr handler both receive the
rendered events. Quiet mode is a head processor that drops every event;
the plan's `make_filtering_bound_logger(CRITICAL+1)` form is unsupported
by the structlog level table (only {0,10,20,30,40,50} are valid). Direct
`logging.getLogger(...)` outside this module is forbidden (split 11
lints).
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

ROTATING_BYTES_PER_FILE = 10 * 1024 * 1024
ROTATING_BACKUP_COUNT = 3
STDERR_HANDLER_NAME = "kestrel-mock-site-stderr"
ROTATING_HANDLER_NAME = "kestrel-mock-site-rotating"

_lock = threading.Lock()
_configured: bool = False
_active_signature: tuple[bool, str | None, bool] | None = None


def is_configured() -> bool:
    return _configured


def reset_for_tests() -> None:
    """Test-only: reset the one-shot guard.

    Production callers must never invoke this. Tests parametrized over
    multiple settings reconfigure the renderer between cases.
    """
    global _configured, _active_signature
    with _lock:
        _configured = False
        _active_signature = None
        _detach_kestrel_handlers()


def configure_logging(
    *,
    quiet: bool,
    log_file: Path | None,
    json_renderer: bool | None = None,
) -> None:
    """One-shot config; subsequent calls with same args no-op.

    `json_renderer=None` auto-selects: console renderer when stderr is a
    TTY, JSON renderer otherwise. Tests pass an explicit value for stability.
    """
    global _configured, _active_signature
    if json_renderer is None:
        json_renderer = not sys.stderr.isatty()
    signature = (quiet, str(log_file) if log_file else None, json_renderer)
    with _lock:
        if _configured:
            if signature != _active_signature:
                raise RuntimeError(
                    "configure_logging already configured with a different signature; "
                    "call reset_for_tests() in test code only"
                )
            return
        _apply(quiet=quiet, log_file=log_file, json_renderer=json_renderer)
        _configured = True
        _active_signature = signature


def _apply(*, quiet: bool, log_file: Path | None, json_renderer: bool) -> None:
    pre_chain: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _drop_provided_value,
    ]
    head_processors: list[Any] = []
    if quiet:
        head_processors.append(_drop_all)
    structlog.configure(
        processors=[
            *head_processors,
            *pre_chain,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_renderer
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=pre_chain,
    )
    _wire_handlers(formatter=formatter, log_file=log_file)


def _wire_handlers(*, formatter: logging.Formatter, log_file: Path | None) -> None:
    root = logging.getLogger()
    _detach_kestrel_handlers()

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.set_name(STDERR_HANDLER_NAME)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.INFO)
    root.addHandler(stderr_handler)

    if log_file is not None:
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=ROTATING_BYTES_PER_FILE,
            backupCount=ROTATING_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.set_name(ROTATING_HANDLER_NAME)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    root.setLevel(logging.INFO)


def _drop_all(_logger: WrappedLogger, _method_name: str, _event_dict: EventDict) -> EventDict:
    """Quiet-mode head processor: drop every event before render or sink."""
    raise structlog.DropEvent


def _drop_provided_value(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Drop `provided_value` from any log payload.

    Plan section 16 forbids `validation_failure` carrying rejected user
    input. Validators do not pass that key; this processor ensures a defect
    anywhere in the call graph cannot leak PII.
    """
    event_dict.pop("provided_value", None)
    return event_dict


def _detach_kestrel_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() in {STDERR_HANDLER_NAME, ROTATING_HANDLER_NAME}:
            root.removeHandler(handler)
            handler.close()
