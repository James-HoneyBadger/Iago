"""Exact endgame solving.

The searcher already extends to a full solve once the empty count drops below a
threshold; this module exposes that capability as a small standalone API and
provides a brute-force reference used by the tests.
"""

from __future__ import annotations

from typing import Optional

from ..core.bitboard import Position
from .search import SearchLimits, SearchResult, Searcher

MAX_EXACT_EMPTIES = 24


def solve(position: Position, time_limit: float = 10.0) -> SearchResult:
    """Solve *position* to the end (disc difference), returning the best move."""

    searcher = Searcher(position.size, seed=0)
    limits = SearchLimits(
        time_limit=time_limit,
        max_depth=position.empty_count() + 1,
        endgame_empties=MAX_EXACT_EMPTIES,
    )
    return searcher.search(position, limits)


def perfect_difference(position: Position) -> int:
    """Exact final disc difference from the side to move's point of view.

    Reference implementation without pruning; only suitable for the last few
    moves, which is exactly what the tests use it for.
    """

    moves = position.legal_moves()
    if not moves:
        if not position.geometry.move_mask(position.other, position.own):
            return position.own.bit_count() - position.other.bit_count()
        return -perfect_difference(position.pass_turn())

    best = -(position.size * position.size)
    for index in range(position.size * position.size):
        if not (moves >> index) & 1:
            continue
        best = max(best, -perfect_difference(position.apply_index(index)))
    return best


def best_move_exact(
    position: Position, time_limit: float = 10.0
) -> Optional[tuple[int, int]]:
    return solve(position, time_limit).move


__all__ = [
    "MAX_EXACT_EMPTIES",
    "best_move_exact",
    "perfect_difference",
    "solve",
]
