"""Exception hierarchy for Iago Deluxe.

Every error raised deliberately by the application derives from
:class:`IagoError`, so callers can distinguish expected failures from bugs.
"""


class IagoError(Exception):
    """Base class for all application errors."""


class BoardError(IagoError):
    """Raised when a board operation is invalid."""


class IllegalMoveError(BoardError):
    """Raised when a move is not legal for the specified player."""


class AIError(IagoError):
    """Raised when the engine cannot produce a move."""


class SearchCancelled(AIError):
    """Raised internally when an in-flight search is abandoned."""


class PersistenceError(IagoError):
    """Base class for storage problems."""


class SaveFileError(PersistenceError):
    """Raised when a save file is missing, malformed or unsupported."""


class SettingsError(PersistenceError):
    """Raised when settings cannot be read or validated."""


class AssetError(IagoError):
    """Raised when a font, texture or other asset cannot be prepared."""


class AudioError(IagoError):
    """Raised when the audio subsystem is unavailable."""


__all__ = [
    "IagoError",
    "BoardError",
    "IllegalMoveError",
    "AIError",
    "SearchCancelled",
    "PersistenceError",
    "SaveFileError",
    "SettingsError",
    "AssetError",
    "AudioError",
]
