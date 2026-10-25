"""Difficulty presets.

A level bundles the search budget with behaviour tweaks so the five settings
feel meaningfully different rather than just "slower for longer".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Level:
    """Search configuration for one difficulty setting."""

    number: int
    name: str
    time_limit: float
    max_depth: int
    endgame_empties: int
    random_move_chance: float
    noise: int
    use_book: bool
    description: str

    @property
    def is_random(self) -> bool:
        return self.random_move_chance >= 1.0


LEVELS: Dict[int, Level] = {
    1: Level(
        number=1,
        name="Easy",
        time_limit=0.0,
        max_depth=0,
        endgame_empties=0,
        random_move_chance=1.0,
        noise=0,
        use_book=False,
        description="Plays a random legal move. Perfect for learning the rules.",
    ),
    2: Level(
        number=2,
        name="Medium",
        time_limit=0.0,
        max_depth=1,
        endgame_empties=0,
        random_move_chance=0.0,
        noise=90,
        use_book=False,
        description="Instant greedy evaluation; occasionally overlooks a trap.",
    ),
    3: Level(
        number=3,
        name="Hard",
        time_limit=0.6,
        max_depth=12,
        endgame_empties=4,
        random_move_chance=0.0,
        noise=18,
        use_book=True,
        description="Real alpha-beta search with a short thinking budget.",
    ),
    4: Level(
        number=4,
        name="Expert",
        time_limit=2.5,
        max_depth=24,
        endgame_empties=12,
        random_move_chance=0.0,
        noise=0,
        use_book=True,
        description="Deep search, transposition table and exact endgames.",
    ),
    5: Level(
        number=5,
        name="Master",
        time_limit=5.0,
        max_depth=40,
        endgame_empties=18,
        random_move_chance=0.0,
        noise=0,
        use_book=True,
        description="Tournament settings: long search with a perfect endgame solver.",
    ),
}

MAX_DIFFICULTY = max(LEVELS)
DIFFICULTY_NAMES: Tuple[str, ...] = tuple(LEVELS[i].name for i in sorted(LEVELS))


def get_level(number: int) -> Level:
    """Return the preset for *number*, clamped into the supported range."""

    if number not in LEVELS:
        number = min(max(number, 1), MAX_DIFFICULTY)
    return LEVELS[number]


__all__ = [
    "DIFFICULTY_NAMES",
    "LEVELS",
    "Level",
    "MAX_DIFFICULTY",
    "get_level",
]
