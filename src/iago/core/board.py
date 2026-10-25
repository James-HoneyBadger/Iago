"""Reference (list-based) Reversi rules.

This is the authoritative rules implementation used by the interface.  It is
deliberately simple and readable; the AI searches on
:class:`iago.core.bitboard.Position` instead.  A fuzz suite proves the two agree
on every legal move and flip set.

``grid`` is a mutable ``grid[row][col]`` list of lists holding ``EMPTY``,
``PLAYER_BLACK`` or ``PLAYER_WHITE``.  Callers (the session layer) may assign a
fresh grid to restore a position, which is why ``grid`` is a plain attribute
rather than a computed property.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .bitboard import Position
from .constants import (
    DEFAULT_BOARD_SIZE,
    DIRECTIONS,
    EMPTY,
    PLAYER_BLACK,
    PLAYER_WHITE,
    opponent,
)


class Board:
    """Mutable Reversi board with the classic public API."""

    __slots__ = ("size", "grid", "current_player", "game_over", "winner")

    def __init__(self, size: int = DEFAULT_BOARD_SIZE) -> None:
        if size < 4:
            raise ValueError(f"Unsupported board size: {size}")
        self.size = size
        self.grid: List[List[int]] = []
        self.current_player = PLAYER_BLACK
        self.game_over = False
        self.winner: Optional[int] = None
        self.reset()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Return the board to its initial four-disc arrangement."""

        size = self.size
        self.grid = [[EMPTY for _ in range(size)] for _ in range(size)]
        center = size // 2
        self.grid[center - 1][center - 1] = PLAYER_WHITE
        self.grid[center - 1][center] = PLAYER_BLACK
        self.grid[center][center - 1] = PLAYER_BLACK
        self.grid[center][center] = PLAYER_WHITE
        self.current_player = PLAYER_BLACK
        self.game_over = False
        self.winner = None

    @classmethod
    def from_grid(
        cls,
        grid: Sequence[Sequence[int]],
        current_player: int = PLAYER_BLACK,
        game_over: bool = False,
        winner: Optional[int] = None,
    ) -> "Board":
        """Build a board from a nested grid without validating the position."""

        board = cls(len(grid))
        board.grid = [list(row) for row in grid]
        board.current_player = current_player
        board.game_over = game_over
        board.winner = winner
        return board

    def copy(self) -> "Board":
        clone = Board(self.size)
        clone.grid = [row[:] for row in self.grid]
        clone.current_player = self.current_player
        clone.game_over = self.game_over
        clone.winner = self.winner
        return clone

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def is_valid_move(self, row: int, col: int, player: int) -> bool:
        """Return True if *player* may legally play at ``(row, col)``."""

        if not self.in_bounds(row, col):
            return False
        grid = self.grid
        if grid[row][col] != EMPTY:
            return False
        for dr, dc in DIRECTIONS:
            if self._would_flip(row, col, dr, dc, player):
                return True
        return False

    def _would_flip(self, row: int, col: int, dr: int, dc: int, player: int) -> bool:
        """True if playing at ``(row, col)`` flips in direction ``(dr, dc)``."""

        size = self.size
        grid = self.grid
        r = row + dr
        c = col + dc
        enemy = opponent(player)
        seen_enemy = False
        while 0 <= r < size and 0 <= c < size:
            value = grid[r][c]
            if value == EMPTY:
                return False
            if value == enemy:
                seen_enemy = True
            else:
                return seen_enemy
            r += dr
            c += dc
        return False

    def get_valid_moves(self, player: int) -> List[Tuple[int, int]]:
        """Return every legal ``(row, col)`` for *player*."""

        moves: List[Tuple[int, int]] = []
        for row in range(self.size):
            for col in range(self.size):
                if self.is_valid_move(row, col, player):
                    moves.append((row, col))
        return moves

    def legal_move_count(self, player: int) -> int:
        """Cheaper than ``len(get_valid_moves())`` for evaluation code."""

        count = 0
        for row in range(self.size):
            for col in range(self.size):
                if self.is_valid_move(row, col, player):
                    count += 1
        return count

    def _get_flips_direction(
        self, row: int, col: int, dr: int, dc: int, player: int
    ) -> List[Tuple[int, int]]:
        """Opponent discs that would be captured in one direction."""

        size = self.size
        grid = self.grid
        r = row + dr
        c = col + dc
        enemy = opponent(player)
        captured: List[Tuple[int, int]] = []
        while 0 <= r < size and 0 <= c < size:
            value = grid[r][c]
            if value == enemy:
                captured.append((r, c))
            elif value == player:
                return captured
            else:
                break
            r += dr
            c += dc
        return []

    def get_flips(self, row: int, col: int, player: int) -> List[Tuple[int, int]]:
        """Every disc that would flip if *player* played here (no mutation)."""

        if not self.is_valid_move(row, col, player):
            return []
        flips: List[Tuple[int, int]] = []
        for dr, dc in DIRECTIONS:
            flips.extend(self._get_flips_direction(row, col, dr, dc, player))
        return flips

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def _flip_direction(
        self, row: int, col: int, dr: int, dc: int, player: int
    ) -> List[Tuple[int, int]]:
        """Flip one direction, returning the captured cells."""

        captured = self._get_flips_direction(row, col, dr, dc, player)
        grid = self.grid
        for r, c in captured:
            grid[r][c] = player
        return captured

    def make_move(self, row: int, col: int, player: int) -> List[Tuple[int, int]]:
        """Play *player* at ``(row, col)``, flip discs and pass the turn.

        The turn always passes to *player*'s opponent, even when *player* is not
        the side the board currently considers active — replays and analysis
        walk a move log and must not depend on the board's own idea of whose
        turn it is.  Call :meth:`check_game_over` afterwards to apply passes.

        Returns the flipped cells, or an empty list (and no mutation) if the
        move is illegal.
        """

        if not self.is_valid_move(row, col, player):
            return []
        self.grid[row][col] = player
        flipped: List[Tuple[int, int]] = []
        for dr, dc in DIRECTIONS:
            flipped.extend(self._flip_direction(row, col, dr, dc, player))
        self.current_player = opponent(player)
        return flipped

    def switch_player(self) -> None:
        self.current_player = opponent(self.current_player)

    def pass_turn(self) -> None:
        """Explicitly pass (used when a player has no legal move)."""

        self.switch_player()

    # ------------------------------------------------------------------
    # Scoring and termination
    # ------------------------------------------------------------------

    def get_score(self) -> Tuple[int, int]:
        black = sum(row.count(PLAYER_BLACK) for row in self.grid)
        white = sum(row.count(PLAYER_WHITE) for row in self.grid)
        return black, white

    def empty_count(self) -> int:
        return sum(row.count(EMPTY) for row in self.grid)

    def is_full(self) -> bool:
        return all(cell != EMPTY for row in self.grid for cell in row)

    def is_terminal(self) -> bool:
        """True when neither side has a legal move."""

        if self.game_over:
            return True
        return not self.get_valid_moves(PLAYER_BLACK) and not self.get_valid_moves(
            PLAYER_WHITE
        )

    def check_game_over(self) -> bool:
        """Resolve the end of the game or pass the turn.

        * Neither side can move → ``game_over`` and ``winner`` are set.
        * The side to move cannot move → the turn is passed.
        * Otherwise nothing changes.

        Returns True only when the game is freshly declared over.
        """

        black_moves = self.get_valid_moves(PLAYER_BLACK)
        white_moves = self.get_valid_moves(PLAYER_WHITE)

        if not black_moves and not white_moves:
            self.game_over = True
            black_score, white_score = self.get_score()
            if black_score > white_score:
                self.winner = PLAYER_BLACK
            elif white_score > black_score:
                self.winner = PLAYER_WHITE
            else:
                self.winner = 0
            return True

        current_moves = (
            black_moves if self.current_player == PLAYER_BLACK else white_moves
        )
        if not current_moves:
            self.switch_player()
        return False

    # ------------------------------------------------------------------
    # Interop with the bitboard engine
    # ------------------------------------------------------------------

    def to_position(self) -> Position:
        return Position.from_grid(self.grid).with_turn(self.current_player)

    def load_position(self, position: Position) -> None:
        """Replace the contents of this board with *position*."""

        self.size = position.size
        self.grid = position.to_grid()
        self.current_player = position.turn
        self.game_over = False
        self.winner = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        black, white = self.get_score()
        return f"Board(size={self.size}, black={black}, white={white})"


__all__ = ["Board"]
