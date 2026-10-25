"""The public engine facade.

`Engine` owns the difficulty setting, the search engine and the opening book.
It accepts either a :class:`~iago.core.board.Board` or a
:class:`~iago.core.bitboard.Position`.
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from ..core.bitboard import Position
from ..core.board import Board
from ..core.constants import DEFAULT_BOARD_SIZE
from .book import OpeningBook
from .evaluation import evaluate, evaluate_for_black, win_probability
from .levels import LEVELS, MAX_DIFFICULTY, Level, get_level
from .search import SearchLimits, SearchResult, Searcher

BoardLike = Board | Position


def _as_position(board: BoardLike) -> Position:
    if isinstance(board, Position):
        return board
    if hasattr(board, "to_position"):
        return board.to_position()
    raise TypeError(f"Unsupported board type: {type(board)!r}")


class Engine:
    """Reversi engine with five difficulty levels."""

    def __init__(
        self,
        difficulty: int = 2,
        size: int = DEFAULT_BOARD_SIZE,
        seed: Optional[int] = None,
    ) -> None:
        self.size = size
        self._difficulty = difficulty
        self._searcher = Searcher(size, seed=seed)
        self._hint_searcher = Searcher(size, seed=seed)
        self._book = OpeningBook.load(size=size)
        self._rng = random.Random(seed)
        self._log: List[Tuple[int, int, int]] = []

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def difficulty(self) -> int:
        return self._difficulty

    @difficulty.setter
    def difficulty(self, value: int) -> None:
        self._difficulty = int(value)

    @property
    def level(self) -> Level:
        """The active preset (invalid numbers are clamped to the range)."""

        return get_level(self._difficulty)

    @property
    def name(self) -> str:
        preset = LEVELS.get(self._difficulty)
        return preset.name if preset is not None else "?"

    @property
    def book(self) -> OpeningBook:
        return self._book

    def resize(self, size: int) -> None:
        """Switch board size (clears the transposition table)."""

        if size == self.size:
            return
        self.size = size
        seed = self._rng.randrange(1 << 30)
        self._searcher = Searcher(size, seed=seed)
        self._hint_searcher = Searcher(size, seed=seed)
        self._book = OpeningBook.load(size=size)
        self._log.clear()

    def _position_for(self, board: BoardLike) -> Position:
        """Convert a board-like object and keep the engine's tables in sync.

        Loading a save (or switching board size) can hand the engine a position
        whose geometry differs from the one it was built for; resizing here makes
        that impossible to get wrong at the call sites.
        """

        position = _as_position(board)
        if position.size != self.size:
            self.resize(position.size)
        return position

    # ------------------------------------------------------------------
    # Move history (used by the opening book)
    # ------------------------------------------------------------------

    def record_move(self, player: int, row: int, col: int) -> None:
        self._log.append((player, row, col))

    def reset_log(self) -> None:
        self._log.clear()
        self._searcher.clear()

    @property
    def move_log(self) -> Tuple[Tuple[int, int, int], ...]:
        return tuple(self._log)

    # ------------------------------------------------------------------
    # Playing
    # ------------------------------------------------------------------

    def get_move(self, board: BoardLike) -> Optional[Tuple[int, int]]:
        """Return the engine's chosen move for the side to move."""

        position = self._position_for(board)
        moves = position.legal_move_list()
        if not moves:
            return None

        level = self.level
        if level.is_random:
            return self._rng.choice(moves)

        if level.use_book:
            book_move = self._book.lookup(self._log)
            if book_move is not None and book_move in moves:
                return book_move

        result = self._searcher.search(position, self._limits_for(level))
        return result.move or moves[0]

    def quick_hint(self, board: BoardLike) -> Optional[Tuple[int, int]]:
        """Cheap one-ply suggestion, safe to call after every move."""

        position = self._position_for(board)
        if not position.legal_moves():
            return None
        ranked = self._hint_searcher.rank(position, depth=1)
        if not ranked:
            return None
        return divmod(ranked[0][0], position.size)

    def get_hint(
        self, board: BoardLike, time_limit: float = 0.25
    ) -> Optional[Tuple[int, int]]:
        """Return a strong move suggestion without changing engine state."""

        position = self._position_for(board)
        if not position.legal_moves():
            return None
        limits = SearchLimits(
            time_limit=time_limit,
            max_depth=8,
            endgame_empties=10,
        )
        return self._hint_searcher.search(position, limits).move

    def analyse_limits(
        self,
        board: BoardLike,
        limits: SearchLimits,
        progress=None,
    ) -> SearchResult:
        """Run a search with explicit limits on the main search engine."""

        return self._searcher.search(
            self._position_for(board), limits, progress=progress
        )

    def cancel_search(self) -> None:
        """Ask the main search engine to stop as soon as possible."""

        self._searcher.cancel()

    def opening_name(self) -> Optional[str]:
        return self._book.name_for(self._log)

    # ------------------------------------------------------------------
    # Evaluation helpers
    # ------------------------------------------------------------------

    def evaluate(self, board: BoardLike) -> int:
        """Static score from the side to move's perspective."""

        return evaluate(self._position_for(board))

    def evaluate_for_black(self, board: BoardLike) -> int:
        return evaluate_for_black(self._position_for(board))

    def win_probability(self, board: BoardLike) -> float:
        return win_probability(self._position_for(board))

    # ------------------------------------------------------------------

    def _limits_for(self, level: Level) -> SearchLimits:
        return SearchLimits(
            time_limit=level.time_limit,
            max_depth=level.max_depth,
            endgame_empties=level.endgame_empties,
            noise=level.noise,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Engine(level={self.difficulty} {self.name}, size={self.size})"


#: Backwards-compatible alias.
AI = Engine

__all__ = ["AI", "BoardLike", "Engine", "MAX_DIFFICULTY"]
