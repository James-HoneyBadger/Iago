"""Constants shared by the rules engine, the AI and the interface."""

from __future__ import annotations

from typing import Final, Tuple

# ── Cell values ─────────────────────────────────────────────────────────────
EMPTY: Final = 0
PLAYER_BLACK: Final = 1
PLAYER_WHITE: Final = 2
PLAYERS: Final[Tuple[int, int]] = (PLAYER_BLACK, PLAYER_WHITE)

# ── Board geometry ──────────────────────────────────────────────────────────
DEFAULT_BOARD_SIZE: Final = 8
SUPPORTED_BOARD_SIZES: Final[Tuple[int, ...]] = (6, 8, 10)
MIN_BOARD_SIZE: Final = 6
MAX_BOARD_SIZE: Final = 10

#: The eight capture directions as ``(row_delta, col_delta)``.
DIRECTIONS: Final = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)

#: Column labels used by algebraic notation (supports boards up to 12×12).
COLUMN_LETTERS: Final = "abcdefghijkl"

# ── Game modes ──────────────────────────────────────────────────────────────
MODE_HVAI: Final = "hvai"
MODE_HVH: Final = "hvh"
MODE_AVA: Final = "ava"
MODES: Final[Tuple[str, ...]] = (MODE_HVAI, MODE_HVH, MODE_AVA)
MODE_LABELS = {
    MODE_HVAI: "Human vs AI",
    MODE_HVH: "2-Player",
    MODE_AVA: "AI vs AI",
}
MODE_DESCRIPTIONS = {
    MODE_HVAI: "Play against the computer.",
    MODE_HVH: "Two humans share this screen.",
    MODE_AVA: "Watch two engines battle it out.",
}


def opponent(player: int) -> int:
    """Return the opposing colour for a player constant."""

    return PLAYER_WHITE if player == PLAYER_BLACK else PLAYER_BLACK


def player_label(player: int) -> str:
    """Return ``"Black"`` / ``"White"`` for a player constant."""

    return "Black" if player == PLAYER_BLACK else "White"


__all__ = [
    "EMPTY",
    "PLAYER_BLACK",
    "PLAYER_WHITE",
    "PLAYERS",
    "DEFAULT_BOARD_SIZE",
    "SUPPORTED_BOARD_SIZES",
    "MIN_BOARD_SIZE",
    "MAX_BOARD_SIZE",
    "DIRECTIONS",
    "COLUMN_LETTERS",
    "MODE_HVAI",
    "MODE_HVH",
    "MODE_AVA",
    "MODES",
    "MODE_LABELS",
    "MODE_DESCRIPTIONS",
    "opponent",
    "player_label",
]
