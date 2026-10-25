"""Logging configuration.

A single call to :func:`configure` wires up a console handler plus an optional
rotating file handler.  Every module uses :func:`get_logger` so log records are
namespaced under ``iago.*``.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

ROOT_LOGGER_NAME = "iago"
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"
_MAX_BYTES = 512 * 1024
_BACKUP_COUNT = 3


def configure(
    *,
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """Configure the ``iago`` logger tree and return the root logger.

    Idempotent: existing handlers are replaced, so calling it twice is safe.
    """

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            logger.addHandler(file_handler)
        except OSError as exc:  # pragma: no cover - depends on the filesystem
            logger.warning("Could not open log file %s: %s", log_file, exc)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger (``iago.<name>``)."""

    if name == ROOT_LOGGER_NAME or name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


# A default configuration so library users get sane output without opting in.
configure()

__all__ = ["configure", "get_logger", "ROOT_LOGGER_NAME"]
