"""Core game model: constants, bitboards, the reference board and notation."""

from .board import Board
from .bitboard import Geometry, Position, iter_bits
from .constants import (
    DEFAULT_BOARD_SIZE,
    EMPTY,
    MODE_AVA,
    MODE_HVAI,
    MODE_HVH,
    MODES,
    MODE_LABELS,
    PLAYER_BLACK,
    PLAYER_WHITE,
    PLAYERS,
    SUPPORTED_BOARD_SIZES,
    opponent,
)

__all__ = [
    "Board",
    "Geometry",
    "Position",
    "iter_bits",
    "DEFAULT_BOARD_SIZE",
    "EMPTY",
    "MODE_AVA",
    "MODE_HVAI",
    "MODE_HVH",
    "MODES",
    "MODE_LABELS",
    "PLAYER_BLACK",
    "PLAYER_WHITE",
    "PLAYERS",
    "SUPPORTED_BOARD_SIZES",
    "opponent",
]
