"""Static position evaluation.

The score is always from the perspective of the side to move.  Weights are
interpolated between an opening and an endgame profile, because the value of a
disc, of mobility and of parity changes dramatically as the board fills up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.bitboard import Geometry, Position
from ..core.constants import PLAYER_BLACK

#: Empty-square counts between which weights are interpolated.
_OPENING_EMPTIES = 48
_ENDGAME_EMPTIES = 12


@dataclass(frozen=True)
class Weights:
    """Evaluation weights for one phase of the game."""

    mobility: int
    potential: int
    frontier: int
    corner: int
    stability: int
    discs: int
    parity: int


#: Weight profiles.  Opening: mobility and structure dominate.  Endgame: discs
#: and parity decide the result.
OPENING_WEIGHTS = Weights(
    mobility=190, potential=45, frontier=38, corner=240, stability=70, discs=2, parity=0
)
ENDGAME_WEIGHTS = Weights(
    mobility=45,
    potential=10,
    frontier=12,
    corner=180,
    stability=95,
    discs=28,
    parity=34,
)

#: Score returned for a forced win/loss is ``|difference| * TERMINAL_FACTOR``
#: plus this bonus, so a win is always better than any static advantage.
TERMINAL_BONUS = 100_000_000


def _weights(empties: int) -> Weights:
    if empties >= _OPENING_EMPTIES:
        return OPENING_WEIGHTS
    if empties <= _ENDGAME_EMPTIES:
        return ENDGAME_WEIGHTS
    span = _OPENING_EMPTIES - _ENDGAME_EMPTIES
    t = (empties - _ENDGAME_EMPTIES) / span
    return Weights(
        mobility=int(
            ENDGAME_WEIGHTS.mobility
            + (OPENING_WEIGHTS.mobility - ENDGAME_WEIGHTS.mobility) * t
        ),
        potential=int(
            ENDGAME_WEIGHTS.potential
            + (OPENING_WEIGHTS.potential - ENDGAME_WEIGHTS.potential) * t
        ),
        frontier=int(
            ENDGAME_WEIGHTS.frontier
            + (OPENING_WEIGHTS.frontier - ENDGAME_WEIGHTS.frontier) * t
        ),
        corner=int(
            ENDGAME_WEIGHTS.corner
            + (OPENING_WEIGHTS.corner - ENDGAME_WEIGHTS.corner) * t
        ),
        stability=int(
            ENDGAME_WEIGHTS.stability
            + (OPENING_WEIGHTS.stability - ENDGAME_WEIGHTS.stability) * t
        ),
        discs=int(
            ENDGAME_WEIGHTS.discs + (OPENING_WEIGHTS.discs - ENDGAME_WEIGHTS.discs) * t
        ),
        parity=int(
            ENDGAME_WEIGHTS.parity
            + (OPENING_WEIGHTS.parity - ENDGAME_WEIGHTS.parity) * t
        ),
    )


@dataclass(frozen=True)
class CornerTables:
    """Pre-computed corner-related masks for one board size."""

    corners: tuple[int, ...]
    x_squares: tuple[int, ...]
    c_squares: tuple[int, ...]


_CORNER_TABLES: dict[int, CornerTables] = {}


def corner_tables(geometry: Geometry) -> CornerTables:
    size = geometry.size
    table = _CORNER_TABLES.get(size)
    if table is not None:
        return table

    def bit(row: int, col: int) -> int:
        return 1 << (row * size + col)

    corners = (
        bit(0, 0),
        bit(0, size - 1),
        bit(size - 1, 0),
        bit(size - 1, size - 1),
    )
    x_squares = (
        bit(1, 1),
        bit(1, size - 2),
        bit(size - 2, 1),
        bit(size - 2, size - 2),
    )
    c_squares = (
        bit(0, 1),
        bit(1, 0),
        bit(0, size - 2),
        bit(1, size - 1),
        bit(size - 2, 0),
        bit(size - 1, 1),
        bit(size - 2, size - 1),
        bit(size - 1, size - 2),
    )
    table = CornerTables(corners=corners, x_squares=x_squares, c_squares=c_squares)
    _CORNER_TABLES[size] = table
    return table


def count_bits(value: int) -> int:
    return value.bit_count()


def edge_discs(own: int, geometry: Geometry) -> int:
    """Number of *own* discs on the outer ring."""

    size = geometry.size
    mask = geometry.column_masks[0] | geometry.column_masks[size - 1]
    mask |= (1 << size) - 1
    mask |= ((1 << size) - 1) << (size * (size - 1))
    return (own & mask).bit_count()


def stability(own: int, geometry: Geometry) -> int:
    """Cheap stability estimate: corners plus edge discs anchored to corners.

    True stability analysis is expensive; this measures the part that matters
    most in practice — discs that can never be flipped again.
    """

    size = geometry.size
    value = 0
    owned = own
    tables = corner_tables(geometry)

    for corner in tables.corners:
        if not owned & corner:
            continue
        value += 6
        index = corner.bit_length() - 1
        row, col = divmod(index, size)
        row_dir = 1 if row == 0 else -1
        col_dir = 1 if col == 0 else -1
        # Walk both edges out of the corner and count the anchored run.
        for dr, dc in ((row_dir, 0), (0, col_dir)):
            r, c = row + dr, col + dc
            while 0 <= r < size and 0 <= c < size:
                if not owned & (1 << (r * size + c)):
                    break
                value += 2
                r += dr
                c += dc
    return value


def evaluate(position: Position, own_moves: int | None = None) -> int:
    """Score *position* from the perspective of the side to move.

    ``own_moves`` may be supplied by the caller when it already holds the legal
    move mask for the side to move (the search usually does), saving a full
    move generation per leaf node.
    """

    geometry = position.geometry
    full = geometry.full
    turn = position.turn
    own = position.black if turn == PLAYER_BLACK else position.white
    other = position.white if turn == PLAYER_BLACK else position.black
    occupied = own | other
    empty = full & ~occupied
    empties = empty.bit_count()

    weights = _weights(empties)
    tables = corner_tables(geometry)

    my_moves = position.legal_moves() if own_moves is None else own_moves
    opp_moves = geometry.move_mask(other, own)
    mobility = my_moves.bit_count() - opp_moves.bit_count()

    neighbours = geometry.spread(empty)
    my_potential = (neighbours & other).bit_count()
    opp_potential = (neighbours & own).bit_count()
    potential = my_potential - opp_potential

    frontier = (own & neighbours).bit_count() - (other & neighbours).bit_count()

    empty_corners = 0
    for corner in tables.corners:
        if not occupied & corner:
            empty_corners += 1

    corner_value = (own & _mask_of(tables.corners)).bit_count() - (
        other & _mask_of(tables.corners)
    ).bit_count()

    x_penalty = 0
    c_penalty = 0
    if empty_corners:
        x_penalty = (own & _mask_of(tables.x_squares)).bit_count() - (
            other & _mask_of(tables.x_squares)
        ).bit_count()
        c_penalty = (own & _mask_of(tables.c_squares)).bit_count() - (
            other & _mask_of(tables.c_squares)
        ).bit_count()

    stable = stability(own, geometry) - stability(other, geometry)

    discs = own.bit_count() - other.bit_count()

    parity = 0
    if empties <= 16:
        parity = 1 if empties % 2 else -1

    score = (
        mobility * weights.mobility
        + potential * weights.potential
        - frontier * weights.frontier
        + corner_value * weights.corner
        - x_penalty * weights.corner * 3 // 4
        - c_penalty * weights.corner // 3
        + stable * weights.stability
        + discs * weights.discs
        + parity * weights.parity
    )
    return score


_MASK_CACHE: dict[tuple[int, ...], int] = {}


def _mask_of(squares: tuple[int, ...]) -> int:
    mask = _MASK_CACHE.get(squares)
    if mask is None:
        mask = 0
        for square in squares:
            mask |= square
        _MASK_CACHE[squares] = mask
    return mask


def terminal_score(own_discs: int, other_discs: int) -> int:
    """Exact score for a finished game from the side to move's point of view."""

    difference = own_discs - other_discs
    if difference == 0:
        return 0
    return difference * 1000 + (TERMINAL_BONUS if difference > 0 else -TERMINAL_BONUS)


def evaluate_for_black(position: Position) -> int:
    """Evaluation from Black's point of view, for the win-probability bar."""

    raw = evaluate(position)
    return raw if position.turn == PLAYER_BLACK else -raw


def win_probability(position: Position) -> float:
    """Estimate Black's winning chance in ``[0, 1]``.

    Uses the static evaluation early and blends towards the actual disc
    difference once the board is nearly full (where the result is close to
    decided).
    """

    if position.is_terminal():
        black, white = position.score()
        if black > white:
            return 1.0
        if white > black:
            return 0.0
        return 0.5

    score = evaluate_for_black(position)
    logistic = 1.0 / (1.0 + math.exp(-score / 900.0))

    empties = position.empty_count()
    if empties <= 10:
        black, white = position.score()
        total = black + white
        disc_share = black / total if total else 0.5
        trust = (10 - empties) / 10.0
        return logistic * (1.0 - trust) + disc_share * trust
    return logistic


__all__ = [
    "ENDGAME_WEIGHTS",
    "OPENING_WEIGHTS",
    "TERMINAL_BONUS",
    "Weights",
    "corner_tables",
    "count_bits",
    "edge_discs",
    "evaluate",
    "evaluate_for_black",
    "stability",
    "terminal_score",
    "win_probability",
]
