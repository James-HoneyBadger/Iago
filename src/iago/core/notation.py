"""Algebraic notation and opening identification.

Squares are written with a column letter and a 1-based row number counted from
the top of the board (``a1`` is the top-left square), matching the coordinate
labels drawn around the board.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from .constants import COLUMN_LETTERS, DEFAULT_BOARD_SIZE

Move = Tuple[int, int]


def move_name(row: int, col: int) -> str:
    """Return the algebraic name of a square, e.g. ``(2, 3)`` → ``"d3"``."""

    if row < 0 or col < 0 or col >= len(COLUMN_LETTERS):
        raise ValueError(f"Square out of range: ({row}, {col})")
    return f"{COLUMN_LETTERS[col]}{row + 1}"


def parse_move(text: str) -> Move:
    """Parse ``"d3"`` into ``(2, 3)``; raises :class:`ValueError` when invalid."""

    cleaned = text.strip().lower()
    if len(cleaned) < 2:
        raise ValueError(f"Invalid square: {text!r}")
    letter = cleaned[0]
    digits = cleaned[1:]
    if letter not in COLUMN_LETTERS or not digits.isdigit():
        raise ValueError(f"Invalid square: {text!r}")
    row = int(digits) - 1
    if row < 0:
        raise ValueError(f"Invalid square: {text!r}")
    return row, COLUMN_LETTERS.index(letter)


def move_names(moves: Iterable[Tuple[int, int, int]]) -> list[str]:
    """Convert ``(player, row, col)`` triples into algebraic names."""

    return [move_name(row, col) for _, row, col in moves]


def sequence_to_string(moves: Iterable[Tuple[int, int, int]]) -> str:
    """Render a game as ``"d3 e3 c4 ..."``."""

    return " ".join(move_names(moves))


@dataclass(frozen=True)
class Opening:
    """A named opening line."""

    name: str
    moves: Tuple[str, ...]
    description: str = ""


#: Conventional Othello opening names for the eight-by-eight board.  The book
#: in :mod:`iago.ai.book` uses the same line identifiers.
OPENINGS: Tuple[Opening, ...] = (
    Opening("Tiger", ("d3", "e3"), "Black takes the diagonal, White blocks."),
    Opening("Cat", ("c4", "c3"), "Parallel diagonal build on the c-file."),
    Opening("Horse", ("f5", "f4"), "Mirror of the Tiger on the f-file."),
    Opening("Rabbit", ("e6", "d6"), "Quiet central exchange."),
    Opening("Bull", ("d3", "c3"), "Tiger move answered off the diagonal."),
    Opening("Raccoon", ("c4", "e3"), "Cat move answered on the other flank."),
)

_OPENING_BY_LINE = {opening.moves: opening for opening in OPENINGS}


def identify_opening(
    moves: Sequence[Tuple[int, int, int]], size: int = DEFAULT_BOARD_SIZE
) -> Optional[Opening]:
    """Return the named opening matching the longest prefix of *moves*."""

    if size != DEFAULT_BOARD_SIZE or not moves:
        return None
    names = tuple(move_names(moves))
    best: Optional[Opening] = None
    for length in range(1, len(names) + 1):
        opening = _OPENING_BY_LINE.get(names[:length])
        if opening is not None:
            best = opening
    return best


def opening_label(
    moves: Sequence[Tuple[int, int, int]], size: int = DEFAULT_BOARD_SIZE
) -> Optional[str]:
    """Human-readable opening label, or ``None`` when not in the book."""

    opening = identify_opening(moves, size)
    return opening.name if opening else None


__all__ = [
    "Move",
    "Opening",
    "OPENINGS",
    "identify_opening",
    "move_name",
    "move_names",
    "opening_label",
    "parse_move",
    "sequence_to_string",
]
