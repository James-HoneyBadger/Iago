"""Size-generic bitboard representation of a Reversi position.

Squares are numbered row-major (``index = row * size + col``) and stored as bit
``1 << index`` in a Python ``int``.  Python integers are arbitrary precision, so
a single implementation serves 6×6, 8×8 and 10×10 boards without special cases.

Move generation uses the classic shift-and-mask technique: for each of the eight
directions, shift the mover's discs, intersect with enemy discs, propagate the
run by repeated shifts (doubling the reach each time), then intersect with the
empty squares.  Positions are immutable; :meth:`Position.apply` returns a new
position and maintains an incremental Zobrist hash.
"""

from __future__ import annotations

import random
from typing import Iterator, List, Sequence, Tuple

from .constants import (
    DEFAULT_BOARD_SIZE,
    DIRECTIONS,
    EMPTY,
    PLAYER_BLACK,
    PLAYER_WHITE,
    opponent,
)

#: Number of doubling steps needed to cover a contiguous run on any board we
#: support (5 steps reach 32 discs; the longest possible run is ``size - 2``).
_RUN_STEPS = 5


def iter_bits(mask: int) -> Iterator[int]:
    """Yield the indices of the set bits in *mask*, lowest first."""

    while mask:
        lsb = mask & -mask
        yield lsb.bit_length() - 1
        mask ^= lsb


def mask_to_cells(mask: int, size: int) -> List[Tuple[int, int]]:
    """Convert a bit mask into a list of ``(row, col)`` pairs."""

    return [(index // size, index % size) for index in iter_bits(mask)]


class Geometry:
    """Pre-computed masks and Zobrist keys for one board size.

    Instances are cached by :func:`geometry_for`, so construction happens at
    most once per size per process.
    """

    __slots__ = (
        "size",
        "full",
        "shifts",
        "column_masks",
        "zobrist_keys",
        "zobrist_turn",
    )

    def __init__(self, size: int) -> None:
        if size < 4 or size > 12:
            raise ValueError(f"Unsupported board size: {size}")
        self.size = size
        self.full = (1 << (size * size)) - 1

        columns: List[int] = []
        for col in range(size):
            column = 0
            for row in range(size):
                column |= 1 << (row * size + col)
            columns.append(column)
        self.column_masks = tuple(columns)

        shifts: List[Tuple[int, int, bool]] = []
        for dr, dc in DIRECTIONS:
            delta = dr * size + dc
            if dc == 0:
                mask = self.full
            elif dc > 0:
                mask = 0
                for col in range(0, size - dc):
                    mask |= columns[col]
            else:
                mask = 0
                for col in range(-dc, size):
                    mask |= columns[col]
            if delta > 0:
                shifts.append((delta, mask, True))
            else:
                shifts.append((-delta, mask, False))
        self.shifts = tuple(shifts)

        # Deterministic keys keep transposition tables reproducible across runs.
        rng = random.Random(0x1A600000 + size)  # nosec B311 - not cryptographic
        squares = size * size
        self.zobrist_keys = (
            tuple(rng.getrandbits(64) for _ in range(squares)),
            tuple(rng.getrandbits(64) for _ in range(squares)),
        )
        self.zobrist_turn = rng.getrandbits(64)

    # -- hot paths ---------------------------------------------------------

    def move_mask(self, own: int, opp: int) -> int:
        """Return the bit mask of legal moves for the side owning *own*."""

        full = self.full
        empty = full & ~(own | opp)
        moves = 0
        for delta, mask, left in self.shifts:
            if left:
                x = ((own & mask) << delta) & full & opp
                if not x:
                    continue
                # Walk the contiguous enemy run; stop when it stops growing.
                while True:
                    grown = x | (((x & mask) << delta) & full & opp)
                    if grown == x:
                        break
                    x = grown
                moves |= ((x & mask) << delta) & full & empty
            else:
                x = ((own & mask) >> delta) & opp
                if not x:
                    continue
                while True:
                    grown = x | (((x & mask) >> delta) & opp)
                    if grown == x:
                        break
                    x = grown
                moves |= ((x & mask) >> delta) & empty
        return moves

    def flips(self, own: int, opp: int, move: int) -> int:
        """Return the mask of discs flipped by playing *move* (a single bit)."""

        captured = 0
        full = self.full
        for delta, mask, left in self.shifts:
            if left:
                x = ((move & mask) << delta) & full & opp
                if not x:
                    continue
                while True:
                    grown = x | (((x & mask) << delta) & full & opp)
                    if grown == x:
                        break
                    x = grown
                if ((x & mask) << delta) & full & own:
                    captured |= x
            else:
                x = ((move & mask) >> delta) & opp
                if not x:
                    continue
                while True:
                    grown = x | (((x & mask) >> delta) & opp)
                    if grown == x:
                        break
                    x = grown
                if ((x & mask) >> delta) & own:
                    captured |= x
        return captured

    def spread(self, bits: int) -> int:
        """Return every square in the 8-neighbourhood of *bits*."""

        full = self.full
        out = 0
        for delta, mask, left in self.shifts:
            if left:
                out |= ((bits & mask) << delta) & full
            else:
                out |= (bits & mask) >> delta
        return out

    def index(self, row: int, col: int) -> int:
        return row * self.size + col


_GEOMETRY_CACHE: dict[int, Geometry] = {}


def geometry_for(size: int) -> Geometry:
    """Return (and cache) the geometry tables for *size*."""

    geo = _GEOMETRY_CACHE.get(size)
    if geo is None:
        geo = Geometry(size)
        _GEOMETRY_CACHE[size] = geo
    return geo


class Position:
    """An immutable Reversi position.

    Construct the starting position with ``Position()`` or ``Position(6)``, or
    build one from a grid with :meth:`from_grid`.
    """

    __slots__ = (
        "size",
        "geometry",
        "black",
        "white",
        "turn",
        "zobrist",
        "_legal",
    )

    def __init__(
        self,
        size: int = DEFAULT_BOARD_SIZE,
        black: int | None = None,
        white: int | None = None,
        turn: int = PLAYER_BLACK,
    ) -> None:
        self.size = size
        self.geometry = geometry_for(size)
        if black is None or white is None:
            black, white = _initial_masks(size)
        self.black = black
        self.white = white
        self.turn = turn
        self.zobrist = self._compute_zobrist()
        self._legal: int | None = None

    # -- construction ------------------------------------------------------

    @classmethod
    def _make(
        cls, size: int, black: int, white: int, turn: int, zobrist: int
    ) -> "Position":
        pos = object.__new__(cls)
        pos.size = size
        pos.geometry = geometry_for(size)
        pos.black = black
        pos.white = white
        pos.turn = turn
        pos.zobrist = zobrist
        pos._legal = None
        return pos

    @classmethod
    def from_grid(cls, grid: Sequence[Sequence[int]]) -> "Position":
        """Build a position from a ``grid[row][col]`` nested sequence."""

        size = len(grid)
        black = 0
        white = 0
        for row in range(size):
            line = grid[row]
            for col in range(size):
                value = line[col]
                if value == PLAYER_BLACK:
                    black |= 1 << (row * size + col)
                elif value == PLAYER_WHITE:
                    white |= 1 << (row * size + col)
        return cls(size, black, white)

    @classmethod
    def from_bits(
        cls, size: int, black: int, white: int, turn: int = PLAYER_BLACK
    ) -> "Position":
        return cls(size, black, white, turn)

    def _compute_zobrist(self) -> int:
        keys = self.geometry.zobrist_keys
        zobrist = 0
        black = self.black
        white = self.white
        while black:
            lsb = black & -black
            zobrist ^= keys[PLAYER_BLACK - 1][lsb.bit_length() - 1]
            black ^= lsb
        while white:
            lsb = white & -white
            zobrist ^= keys[PLAYER_WHITE - 1][lsb.bit_length() - 1]
            white ^= lsb
        if self.turn == PLAYER_WHITE:
            zobrist ^= self.geometry.zobrist_turn
        return zobrist

    # -- basic queries -----------------------------------------------------

    @property
    def own(self) -> int:
        return self.black if self.turn == PLAYER_BLACK else self.white

    @property
    def other(self) -> int:
        return self.white if self.turn == PLAYER_BLACK else self.black

    @property
    def occupied(self) -> int:
        return self.black | self.white

    @property
    def empty_mask(self) -> int:
        return self.geometry.full & ~self.occupied

    def count(self, player: int) -> int:
        return (
            self.black.bit_count() if player == PLAYER_BLACK else self.white.bit_count()
        )

    def score(self) -> Tuple[int, int]:
        """Return ``(black_discs, white_discs)``."""

        return self.black.bit_count(), self.white.bit_count()

    def empty_count(self) -> int:
        return self.size * self.size - (self.black | self.white).bit_count()

    def move_number(self) -> int:
        """1-based ply number (the initial position is ply 1)."""

        return self.size * self.size - self.empty_count() - 3

    def disc_at(self, row: int, col: int) -> int:
        bit = 1 << (row * self.size + col)
        if self.black & bit:
            return PLAYER_BLACK
        if self.white & bit:
            return PLAYER_WHITE
        return EMPTY

    def to_grid(self) -> List[List[int]]:
        size = self.size
        grid = [[EMPTY] * size for _ in range(size)]
        for index in iter_bits(self.black):
            grid[index // size][index % size] = PLAYER_BLACK
        for index in iter_bits(self.white):
            grid[index // size][index % size] = PLAYER_WHITE
        return grid

    # -- move generation ---------------------------------------------------

    def legal_moves(self) -> int:
        """Return the bit mask of legal moves for the side to move.

        Positions are immutable, so the result is cached on first use.
        """

        mask = self._legal
        if mask is None:
            mask = self.geometry.move_mask(self.own, self.other)
            self._legal = mask
        return mask

    def legal_move_list(self) -> List[Tuple[int, int]]:
        return mask_to_cells(self.legal_moves(), self.size)

    def has_moves(self) -> bool:
        return self.legal_moves() != 0

    def is_legal(self, row: int, col: int) -> bool:
        if not (0 <= row < self.size and 0 <= col < self.size):
            return False
        bit = 1 << (row * self.size + col)
        return bool(self.legal_moves() & bit)

    def flips_for(self, row: int, col: int) -> int:
        """Return the mask of discs flipped by playing at ``(row, col)``."""

        bit = 1 << (row * self.size + col)
        if not bit & self.legal_moves():
            return 0
        return self.geometry.flips(self.own, self.other, bit)

    def flips_for_index(self, index: int) -> int:
        bit = 1 << index
        if not bit & self.legal_moves():
            return 0
        return self.geometry.flips(self.own, self.other, bit)

    # -- transitions -------------------------------------------------------

    def apply_index(self, index: int) -> "Position":
        """Play the move at *index* and return the resulting position."""

        return self._apply_bit(1 << index)

    def apply(self, row: int, col: int) -> "Position":
        return self._apply_bit(1 << (row * self.size + col))

    def _apply_bit(self, bit: int) -> "Position":
        turn = self.turn
        if turn == PLAYER_BLACK:
            own, opp = self.black, self.white
        else:
            own, opp = self.white, self.black

        flips = self.geometry.flips(own, opp, bit)
        if not flips:
            raise ValueError("Illegal move")

        new_own = own | bit | flips
        new_opp = opp & ~flips

        keys = self.geometry.zobrist_keys
        zobrist = self.zobrist ^ self.geometry.zobrist_turn
        zobrist ^= keys[turn - 1][bit.bit_length() - 1]
        other_keys = keys[opponent(turn) - 1]
        own_keys = keys[turn - 1]
        remaining = flips
        while remaining:
            lsb = remaining & -remaining
            index = lsb.bit_length() - 1
            zobrist ^= own_keys[index] ^ other_keys[index]
            remaining ^= lsb

        if turn == PLAYER_BLACK:
            return Position._make(self.size, new_own, new_opp, opponent(turn), zobrist)
        return Position._make(self.size, new_opp, new_own, opponent(turn), zobrist)

    def pass_turn(self) -> "Position":
        """Return a copy with the side to move swapped (a forced pass)."""

        return Position._make(
            self.size,
            self.black,
            self.white,
            opponent(self.turn),
            self.zobrist ^ self.geometry.zobrist_turn,
        )

    def with_turn(self, turn: int) -> "Position":
        """Return a copy with the side to move set to *turn*."""

        if turn == self.turn:
            return self
        return Position._make(
            self.size,
            self.black,
            self.white,
            turn,
            self.zobrist ^ self.geometry.zobrist_turn,
        )

    # -- terminal states ---------------------------------------------------

    def is_terminal(self) -> bool:
        if not self.legal_moves():
            return not self.geometry.move_mask(self.other, self.own)
        return False

    def result(self) -> int | None:
        """Return the winner (0 for a draw) or ``None`` if the game continues."""

        if not self.is_terminal():
            return None
        black, white = self.score()
        if black > white:
            return PLAYER_BLACK
        if white > black:
            return PLAYER_WHITE
        return 0

    # -- dunder ------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return NotImplemented
        return (
            self.size == other.size
            and self.black == other.black
            and self.white == other.white
            and self.turn == other.turn
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        black, white = self.score()
        return (
            f"Position(size={self.size}, black={black}, white={white}, "
            f"turn={'B' if self.turn == PLAYER_BLACK else 'W'})"
        )


def _initial_masks(size: int) -> Tuple[int, int]:
    center = size // 2
    layout = (
        ((center - 1, center - 1), PLAYER_WHITE),
        ((center - 1, center), PLAYER_BLACK),
        ((center, center - 1), PLAYER_BLACK),
        ((center, center), PLAYER_WHITE),
    )
    black = 0
    white = 0
    for (row, col), player in layout:
        bit = 1 << (row * size + col)
        if player == PLAYER_BLACK:
            black |= bit
        else:
            white |= bit
    return black, white


__all__ = [
    "DIRECTIONS",
    "Geometry",
    "Position",
    "geometry_for",
    "iter_bits",
    "mask_to_cells",
]
