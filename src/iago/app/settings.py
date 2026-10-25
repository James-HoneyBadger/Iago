"""User settings and persistent statistics, with validation and migration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..ai.levels import MAX_DIFFICULTY
from ..core.constants import (
    DEFAULT_BOARD_SIZE,
    MODE_HVAI,
    MODES,
    PLAYER_BLACK,
    PLAYER_WHITE,
    SUPPORTED_BOARD_SIZES,
)
from ..ui.layout import MAX_UI_SCALE, MIN_UI_SCALE
from ..ui.theme import DEFAULT_THEME_KEY, THEMES

CLOCK_MODES = ("off", "stopwatch", "blitz")
CLOCK_LABELS = {"off": "No clock", "stopwatch": "Stopwatch", "blitz": "Blitz"}


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


@dataclass
class GameSettings:
    """Everything the player can change, persisted between sessions."""

    theme: str = DEFAULT_THEME_KEY
    sound_enabled: bool = True
    sound_volume: float = 0.6
    show_hints: bool = True
    animations: bool = True
    particles: bool = True
    show_coordinates: bool = True
    show_eval_bar: bool = True
    ai_level: int = 3
    mode: str = MODE_HVAI
    player_color: int = PLAYER_BLACK
    board_size: int = DEFAULT_BOARD_SIZE
    clock_mode: str = "off"
    blitz_minutes: int = 5
    blitz_increment: int = 3
    fullscreen: bool = False
    ui_scale: float = 1.0
    window_width: int = 1100
    window_height: int = 800

    # ------------------------------------------------------------------

    def validated(self) -> "GameSettings":
        """Force every field into its legal range and return ``self``.

        Called on load and before every save, so a hand-edited file can never
        leave the game in an impossible state.
        """

        if self.theme not in THEMES:
            self.theme = DEFAULT_THEME_KEY
        if self.mode not in MODES:
            self.mode = MODE_HVAI
        if self.board_size not in SUPPORTED_BOARD_SIZES:
            self.board_size = DEFAULT_BOARD_SIZE
        if self.player_color not in (PLAYER_BLACK, PLAYER_WHITE):
            self.player_color = PLAYER_BLACK
        if self.clock_mode not in CLOCK_MODES:
            self.clock_mode = "off"
        self.ai_level = _clamp(self.ai_level, 1, MAX_DIFFICULTY)
        self.sound_volume = max(0.0, min(1.0, float(self.sound_volume)))
        self.blitz_minutes = _clamp(self.blitz_minutes, 1, 60)
        self.blitz_increment = _clamp(self.blitz_increment, 0, 60)
        self.ui_scale = max(MIN_UI_SCALE, min(MAX_UI_SCALE, float(self.ui_scale)))
        self.window_width = _clamp(self.window_width, 760, 2400)
        self.window_height = _clamp(self.window_height, 660, 1800)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameSettings":
        known = {field_name for field_name in cls.__dataclass_fields__}
        cleaned = {key: value for key, value in data.items() if key in known}
        return cls(**cleaned).validated()

    @classmethod
    def from_legacy(cls, data: Dict[str, Any]) -> "GameSettings":
        """Migrate a v3 settings blob (ai_difficulty as a name, etc.)."""

        difficulty_names = {"EASY": 1, "MEDIUM": 2, "HARD": 3, "EXPERT": 4}
        raw_difficulty = data.get("ai_difficulty", "MEDIUM")
        if isinstance(raw_difficulty, str):
            level = difficulty_names.get(raw_difficulty.upper(), 2)
        else:
            level = _clamp(int(raw_difficulty), 1, MAX_DIFFICULTY)

        return cls(
            theme=DEFAULT_THEME_KEY,
            sound_enabled=bool(data.get("sound_enabled", True)),
            show_hints=bool(data.get("show_hints", True)),
            animations=bool(data.get("animations", True)),
            ai_level=level,
            player_color=int(data.get("player_color", PLAYER_BLACK)),
            board_size=int(data.get("board_size", DEFAULT_BOARD_SIZE)),
            mode=str(data.get("game_mode", MODE_HVAI)),
        ).validated()


@dataclass
class LevelRecord:
    """Per-difficulty results."""

    played: int = 0
    won: int = 0
    lost: int = 0
    drawn: int = 0
    best_score: int = 0

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LevelRecord":
        return cls(
            played=int(data.get("played", 0)),
            won=int(data.get("won", 0)),
            lost=int(data.get("lost", 0)),
            drawn=int(data.get("drawn", 0)),
            best_score=int(data.get("best_score", 0)),
        )


@dataclass
class GameStats:
    """Cumulative statistics and unlocked achievements."""

    games_played: int = 0
    games_won: int = 0
    games_lost: int = 0
    games_drawn: int = 0
    total_moves: int = 0
    best_score: int = 0
    win_streak: int = 0
    loss_streak: int = 0
    current_streak: int = 0
    fastest_win_moves: int = 0
    longest_game_moves: int = 0
    total_time: float = 0.0
    by_level: Dict[int, LevelRecord] = field(default_factory=dict)
    achievements: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------

    def level_record(self, level: int) -> LevelRecord:
        record = self.by_level.get(level)
        if record is None:
            record = LevelRecord()
            self.by_level[level] = record
        return record

    @property
    def win_rate(self) -> float:
        if not self.games_played:
            return 0.0
        return self.games_won / self.games_played

    @property
    def average_moves(self) -> float:
        if not self.games_played:
            return 0.0
        return self.total_moves / self.games_played

    def has_achievement(self, key: str) -> bool:
        return key in self.achievements

    def unlock(self, key: str) -> bool:
        if key in self.achievements:
            return False
        self.achievements.append(key)
        return True

    # ------------------------------------------------------------------

    def record_result(
        self,
        *,
        level: int,
        winner: Optional[int],
        player_color: int,
        moves: int,
        player_score: int,
        opponent_score: int,
        duration: float = 0.0,
    ) -> bool:
        """Record one finished game. Returns True when the player won."""

        self.games_played += 1
        self.total_moves += moves
        self.total_time += duration
        self.longest_game_moves = max(self.longest_game_moves, moves)

        record = self.level_record(level)
        record.played += 1
        record.best_score = max(record.best_score, player_score)

        won = winner == player_color
        if won:
            self.games_won += 1
            record.won += 1
            self.current_streak = max(0, self.current_streak) + 1
            self.win_streak = max(self.win_streak, self.current_streak)
            if self.fastest_win_moves == 0 or moves < self.fastest_win_moves:
                self.fastest_win_moves = moves
        elif winner == 0:
            self.games_drawn += 1
            record.drawn += 1
            self.current_streak = 0
        else:
            self.games_lost += 1
            record.lost += 1
            self.current_streak = min(0, self.current_streak) - 1
            self.loss_streak = max(self.loss_streak, -self.current_streak)

        self.best_score = max(self.best_score, player_score)
        return won

    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["by_level"] = {
            str(level): record.to_dict() for level, record in self.by_level.items()
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameStats":
        by_level: Dict[int, LevelRecord] = {}
        for key, value in (data.get("by_level") or {}).items():
            try:
                by_level[int(key)] = LevelRecord.from_dict(value)
            except (TypeError, ValueError):
                continue
        stats = cls(
            games_played=int(data.get("games_played", 0)),
            games_won=int(data.get("games_won", 0)),
            games_lost=int(data.get("games_lost", 0)),
            games_drawn=int(data.get("games_drawn", 0)),
            total_moves=int(data.get("total_moves", 0)),
            best_score=int(data.get("best_score", 0)),
            win_streak=int(data.get("win_streak", 0)),
            loss_streak=int(data.get("loss_streak", 0)),
            current_streak=int(data.get("current_streak", 0)),
            fastest_win_moves=int(data.get("fastest_win_moves", 0)),
            longest_game_moves=int(data.get("longest_game_moves", 0)),
            total_time=float(data.get("total_time", 0.0)),
            by_level=by_level,
            achievements=list(data.get("achievements", [])),
        )
        return stats


__all__ = [
    "CLOCK_LABELS",
    "CLOCK_MODES",
    "GameSettings",
    "GameStats",
    "LevelRecord",
]
