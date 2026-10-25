"""Reading and writing user data.

Every write is atomic (temporary file + ``os.replace``) and every read is
validated.  Older formats are migrated instead of rejected: a v3 ``stats.json``
or ``saved_game.json`` from Iago 3.0 still loads.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..branding import VERSION
from ..core.board import Board
from ..core.constants import (
    DEFAULT_BOARD_SIZE,
    MODE_HVAI,
    MODES,
    PLAYER_BLACK,
    PLAYER_WHITE,
)
from ..core.notation import move_name
from ..util.errors import SaveFileError, SettingsError
from ..util.log import get_logger
from . import paths
from .settings import GameSettings, GameStats

logger = get_logger("app.persistence")

SAVE_SCHEMA = 4
SETTINGS_SCHEMA = 2
STATS_SCHEMA = 2


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON to *path* atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except OSError:
        try:
            os.unlink(temp_name)
        except OSError:  # pragma: no cover - best effort cleanup
            pass
        raise


def read_json(path: Path) -> Dict[str, Any]:
    """Read a JSON object, raising :class:`SaveFileError` on any problem."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SaveFileError(f"File not found: {path}") from exc
    except OSError as exc:
        raise SaveFileError(f"Cannot read {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SaveFileError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SaveFileError(f"{path} does not contain a JSON object")
    return data


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def load_settings(path: Optional[Path] = None) -> GameSettings:
    """Load settings, migrating legacy files and falling back to defaults."""

    target = path or paths.settings_path()
    if not target.exists():
        legacy = paths.legacy_candidates("settings.json")
        if legacy:
            try:
                data = read_json(legacy[0])
                settings = GameSettings.from_legacy(data.get("settings", data))
                save_settings(settings, target)
                return settings
            except (SaveFileError, TypeError, ValueError) as exc:
                logger.warning("Could not migrate legacy settings: %s", exc)
        return GameSettings().validated()

    try:
        data = read_json(target)
        schema = int(data.get("schema", 1))
        payload = data.get("settings", data)
        if schema >= SETTINGS_SCHEMA:
            return GameSettings.from_dict(payload)
        return GameSettings.from_legacy(payload)
    except (SaveFileError, TypeError, ValueError) as exc:
        logger.warning("Invalid settings at %s (%s); using defaults", target, exc)
        return GameSettings().validated()


def save_settings(settings: GameSettings, path: Optional[Path] = None) -> None:
    target = path or paths.settings_path()
    payload = {
        "schema": SETTINGS_SCHEMA,
        "app_version": VERSION,
        "settings": settings.validated().to_dict(),
    }
    try:
        atomic_write_json(target, payload)
    except OSError as exc:
        raise SettingsError(f"Could not save settings to {target}: {exc}") from exc


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def load_stats(path: Optional[Path] = None) -> GameStats:
    """Load statistics, migrating a v1 file written by Iago 3.0."""

    target = path or paths.stats_path()
    if not target.exists():
        legacy = paths.legacy_candidates("stats.json")
        if legacy:
            try:
                data = read_json(legacy[0])
                stats = _stats_from_payload(data)
                save_stats(stats, target)
                return stats
            except (SaveFileError, TypeError, ValueError) as exc:
                logger.warning("Could not migrate legacy stats: %s", exc)
        return GameStats()

    try:
        return _stats_from_payload(read_json(target))
    except (SaveFileError, TypeError, ValueError) as exc:
        logger.warning("Invalid statistics at %s (%s); starting fresh", target, exc)
        return GameStats()


def _stats_from_payload(data: Dict[str, Any]) -> GameStats:
    payload = data.get("stats", data)
    return GameStats.from_dict(payload)


def save_stats(stats: GameStats, path: Optional[Path] = None) -> None:
    target = path or paths.stats_path()
    payload = {
        "schema": STATS_SCHEMA,
        "app_version": VERSION,
        "stats": stats.to_dict(),
    }
    try:
        atomic_write_json(target, payload)
    except OSError as exc:  # statistics are not worth crashing over
        logger.warning("Could not save statistics to %s: %s", target, exc)


# ---------------------------------------------------------------------------
# Saved games
# ---------------------------------------------------------------------------


@dataclass
class SavedGame:
    """A validated, replayable game."""

    board_size: int = DEFAULT_BOARD_SIZE
    mode: str = MODE_HVAI
    level: int = 3
    player_color: int = PLAYER_BLACK
    moves: List[Tuple[int, int, int]] = field(default_factory=list)
    game_over: bool = False
    winner: Optional[int] = None
    saved_at: str = ""
    app_version: str = VERSION
    schema: int = SAVE_SCHEMA
    clocks: Dict[str, Any] = field(default_factory=dict)

    @property
    def move_count(self) -> int:
        return len(self.moves)

    def replay(self) -> Board:
        """Rebuild the board by replaying the recorded moves."""

        board = Board(self.board_size)
        for index, (player, row, col) in enumerate(self.moves):
            if not board.is_valid_move(row, col, player):
                raise SaveFileError(
                    f"Move {index + 1} ({move_name(row, col)} for player {player}) "
                    "is not legal in this game"
                )
            board.make_move(row, col, player)
            board.check_game_over()
        return board

    def notation(self) -> List[str]:
        return [move_name(row, col) for _, row, col in self.moves]


def build_save_payload(
    *,
    board_size: int,
    mode: str,
    level: int,
    player_color: int,
    moves: List[Tuple[int, int, int]],
    game_over: bool,
    winner: Optional[int],
    clocks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema": SAVE_SCHEMA,
        "app_version": VERSION,
        "saved_at": _timestamp(),
        "board_size": board_size,
        "mode": mode,
        "ai_level": level,
        "player_color": player_color,
        "moves": [
            {"player": player, "row": row, "col": col} for player, row, col in moves
        ],
        "result": {"game_over": game_over, "winner": winner},
        "clocks": clocks or {},
    }


def save_game_file(payload: Dict[str, Any], path: Optional[Path] = None) -> Path:
    target = path or paths.save_path()
    try:
        atomic_write_json(target, payload)
    except OSError as exc:
        raise SaveFileError(f"Could not write {target}: {exc}") from exc
    return target


def load_game(path: Optional[Path] = None) -> SavedGame:
    """Load a saved game from v4 or legacy v3 format."""

    target = path or paths.save_path()
    data = read_json(target)
    return _saved_game_from_payload(data)


def _saved_game_from_payload(data: Dict[str, Any]) -> SavedGame:
    schema = int(data.get("schema", 3))
    game = SavedGame(schema=schema, saved_at=str(data.get("saved_at", "")))

    if schema >= 4:
        game.board_size = int(data.get("board_size", DEFAULT_BOARD_SIZE))
        game.mode = str(data.get("mode", MODE_HVAI))
        game.level = int(data.get("ai_level", 3))
        game.player_color = int(data.get("player_color", PLAYER_BLACK))
        game.clocks = dict(data.get("clocks") or {})
        result = data.get("result") or {}
        game.game_over = bool(result.get("game_over", False))
        winner = result.get("winner")
        game.winner = None if winner is None else int(winner)
        moves = data.get("moves") or []
        for entry in moves:
            if isinstance(entry, dict):
                game.moves.append(
                    (
                        int(entry.get("player", PLAYER_BLACK)),
                        int(entry["row"]),
                        int(entry["col"]),
                    )
                )
            else:  # pragma: no cover - defensive
                raise SaveFileError("Malformed move entry in save file")
    else:
        settings = data.get("settings") or {}
        game.board_size = int(settings.get("board_size", DEFAULT_BOARD_SIZE))
        game.mode = str(settings.get("game_mode", MODE_HVAI))
        game.level = int(settings.get("ai_difficulty", 3))
        game.player_color = int(settings.get("player_color", PLAYER_BLACK))
        game.game_over = bool(data.get("game_over", False))
        winner = data.get("winner")
        game.winner = None if winner is None else int(winner)
        for entry in data.get("move_log") or []:
            player, row, col = entry
            game.moves.append((int(player), int(row), int(col)))

    if game.board_size < 4:
        raise SaveFileError("Save file has an invalid board size")
    if game.mode not in MODES:
        game.mode = MODE_HVAI
    if game.player_color not in (PLAYER_BLACK, PLAYER_WHITE):
        game.player_color = PLAYER_BLACK

    game.replay()  # validates every move
    return game


def find_autosave() -> Optional[Path]:
    """Return the autosave path if a resumable game exists."""

    candidate = paths.autosave_path()
    if candidate.exists():
        return candidate
    legacy = paths.legacy_candidates("autosave.json")
    return legacy[0] if legacy else None


def delete_autosave() -> None:
    for path in (paths.autosave_path(), *paths.legacy_candidates("autosave.json")):
        try:
            path.unlink()
        except OSError:
            continue


__all__ = [
    "SAVE_SCHEMA",
    "SavedGame",
    "atomic_write_json",
    "build_save_payload",
    "delete_autosave",
    "find_autosave",
    "load_game",
    "load_settings",
    "load_stats",
    "read_json",
    "save_game_file",
    "save_settings",
    "save_stats",
]
