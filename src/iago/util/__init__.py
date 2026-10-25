"""Utility helpers: logging and the application exception hierarchy."""

from .errors import (
    AIError,
    AssetError,
    AudioError,
    BoardError,
    IagoError,
    IllegalMoveError,
    PersistenceError,
    SaveFileError,
    SearchCancelled,
    SettingsError,
)
from .log import configure as configure_logging
from .log import get_logger

__all__ = [
    "AIError",
    "AssetError",
    "AudioError",
    "BoardError",
    "IagoError",
    "IllegalMoveError",
    "PersistenceError",
    "SaveFileError",
    "SearchCancelled",
    "SettingsError",
    "configure_logging",
    "get_logger",
]
