"""Filesystem locations for user data.

The application never writes next to its source: settings, statistics, saves
and logs live in the platform's user-data directory.  ``IAGO_DATA_DIR``
overrides the base of that directory (``<base>/iago``), which is what the tests
use.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from ..branding import APP_SLUG, DATA_DIR_NAME

ENV_OVERRIDE = "IAGO_DATA_DIR"


def _base_dir() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()

    home = Path.home()
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return home / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))


def data_dir() -> Path:
    """Return (and create) the application data directory."""

    directory = _base_dir() / DATA_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def settings_path() -> Path:
    return data_dir() / "settings.json"


def stats_path() -> Path:
    return data_dir() / "stats.json"


def autosave_path() -> Path:
    return data_dir() / "autosave.json"


def save_path(name: str = "saved_game") -> Path:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "saved_game"
    return data_dir() / f"{safe}.json"


def log_path() -> Path:
    return data_dir() / f"{APP_SLUG}.log"


def legacy_candidates(filename: str) -> list[Path]:
    """Old versions wrote data next to the source tree; find those files."""

    root = Path(__file__).resolve().parents[3]
    candidates = [root / filename, Path.cwd() / filename]
    return [path for path in candidates if path.exists()]


def find_existing(*paths: Optional[Path]) -> Optional[Path]:
    for path in paths:
        if path is not None and path.exists():
            return path
    return None


__all__ = [
    "ENV_OVERRIDE",
    "autosave_path",
    "data_dir",
    "find_existing",
    "legacy_candidates",
    "log_path",
    "save_path",
    "settings_path",
    "stats_path",
]
