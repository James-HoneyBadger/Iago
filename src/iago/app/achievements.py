"""Achievements.

Each achievement is a pure predicate over the persisted statistics plus a
summary of the game that has just finished, which keeps unlocking logic easy to
test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..ai.levels import MAX_DIFFICULTY
from ..core.constants import PLAYER_BLACK
from .settings import GameStats


@dataclass(frozen=True)
class Achievement:
    key: str
    title: str
    description: str


@dataclass
class GameSummary:
    """Facts about a completed game, used to unlock achievements."""

    mode: str
    level: int
    player_color: int
    winner: Optional[int]
    moves: int
    board_size: int
    black_score: int
    white_score: int
    duration: float = 0.0
    lowest_probability: float = 0.5

    @property
    def player_score(self) -> int:
        return (
            self.black_score if self.player_color == PLAYER_BLACK else self.white_score
        )

    @property
    def opponent_score(self) -> int:
        return (
            self.white_score if self.player_color == PLAYER_BLACK else self.black_score
        )

    @property
    def won(self) -> bool:
        return self.winner == self.player_color


ACHIEVEMENTS: List[Achievement] = [
    Achievement("first_win", "First Blood", "Win your first game."),
    Achievement("ten_wins", "Seasoned", "Win ten games."),
    Achievement("fifty_games", "Devoted", "Finish fifty games."),
    Achievement("beat_master", "Giant Slayer", "Defeat the Master engine."),
    Achievement("perfect_game", "Flawless", "Win while holding every square."),
    Achievement("shutout", "Clean Sheet", "Win without conceding a single disc."),
    Achievement("comeback", "Against the Odds", "Win from under 15% winning chances."),
    Achievement("streak_five", "On Fire", "Win five games in a row."),
    Achievement("quick_win", "Blitz", "Win a game in 40 moves or fewer."),
    Achievement(
        "full_board", "To the Last Disc", "Play a game to a completely full board."
    ),
    Achievement("grand_slam", "Grand Slam", "Beat every difficulty at least once."),
]

ACHIEVEMENTS_BY_KEY = {achievement.key: achievement for achievement in ACHIEVEMENTS}


def _beat_every_level(stats: GameStats) -> bool:
    return all(
        stats.by_level.get(level) is not None and stats.by_level[level].won > 0
        for level in range(1, MAX_DIFFICULTY + 1)
    )


def evaluate(stats: GameStats, summary: GameSummary) -> List[Achievement]:
    """Unlock any newly earned achievements and return them."""

    unlocked: List[Achievement] = []

    def unlock(key: str, condition: bool) -> None:
        if condition and stats.unlock(key):
            unlocked.append(ACHIEVEMENTS_BY_KEY[key])

    unlock("first_win", stats.games_won >= 1)
    unlock("ten_wins", stats.games_won >= 10)
    unlock("fifty_games", stats.games_played >= 50)
    unlock("beat_master", summary.won and summary.level >= MAX_DIFFICULTY)
    unlock(
        "perfect_game",
        summary.won and summary.player_score >= summary.board_size * summary.board_size,
    )
    unlock("shutout", summary.won and summary.opponent_score == 0)
    unlock("comeback", summary.won and summary.lowest_probability <= 0.15)
    unlock("streak_five", stats.win_streak >= 5)
    unlock("quick_win", summary.won and summary.moves <= 40)
    unlock(
        "full_board",
        summary.moves > 0
        and summary.black_score + summary.white_score >= summary.board_size**2,
    )
    unlock("grand_slam", _beat_every_level(stats))
    return unlocked


def progress(stats: GameStats) -> List[tuple[Achievement, bool]]:
    """Return every achievement with its unlocked state."""

    return [
        (achievement, stats.has_achievement(achievement.key))
        for achievement in ACHIEVEMENTS
    ]


__all__ = [
    "ACHIEVEMENTS",
    "ACHIEVEMENTS_BY_KEY",
    "Achievement",
    "GameSummary",
    "evaluate",
    "progress",
]
