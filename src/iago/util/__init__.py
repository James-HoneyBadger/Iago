"""Utility helpers: logging and the application exception hierarchy."""

from .errors import (
    BoardError,
    IagoError,
    IllegalMoveError,
    PersistenceError,
    SaveFileError,
    SettingsError,
)
from .log import configure as configure_logging
from .log import get_logger

__all__ = [
    "BoardError",
    "IagoError",
    "IllegalMoveError",
    "PersistenceError",
    "SaveFileError",
    "SettingsError",
    "configure_logging",
    "get_logger",
]
