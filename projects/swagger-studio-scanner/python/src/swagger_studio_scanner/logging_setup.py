"""Structured logging setup.

structlog renders human-readable output for terminals and JSON for non-TTY
sinks (CI, file capture). One place to configure it; everything else just
calls `structlog.get_logger(__name__)`.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Wire structlog + stdlib logging at the given level."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level.upper(),
    )

    is_tty = sys.stderr.isatty()
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer() if is_tty else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        cache_logger_on_first_use=True,
    )
