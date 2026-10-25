"""Alpha-beta search engine.

Features
--------
* negamax with principal-variation search (PVS)
* Zobrist transposition table with depth-preferred replacement
* iterative deepening with aspiration windows
* adaptive move ordering (TT move, killers, history, static square values)
* exact endgame solving once the empty count drops below a threshold
* soft/hard time management measured with ``time.perf_counter``
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..core.bitboard import Geometry, Position, geometry_for, iter_bits
from ..core.constants import DEFAULT_BOARD_SIZE
from .evaluation import evaluate, terminal_score

INF = 1 << 30
WIN_THRESHOLD = 10_000_000
#: Endgame extensions inside the tree are cheap wins; keep them shallow so that
#: a single iteration can always complete.  Deep solves happen at the root.
_IN_TREE_EXACT = 6

EXACT = 0
LOWER = 1
UPPER = 2

ProgressCallback = Callable[["SearchResult"], None]


class SearchTimeout(Exception):
    """Raised internally when the search budget is exhausted or cancelled."""


@dataclass
class SearchLimits:
    """Constraints for a single search."""

    time_limit: float = 1.0
    max_depth: int = 24
    endgame_empties: int = 12
    noise: int = 0
    node_limit: int = 0


@dataclass
class SearchResult:
    """Outcome of a search."""

    index: Optional[int] = None
    size: int = DEFAULT_BOARD_SIZE
    score: int = 0
    depth: int = 0
    nodes: int = 0
    elapsed: float = 0.0
    pv: List[int] = field(default_factory=list)
    complete: bool = True

    @property
    def move(self) -> Optional[Tuple[int, int]]:
        if self.index is None:
            return None
        return divmod(self.index, self.size)

    @property
    def nps(self) -> float:
        if self.elapsed <= 0:
            return 0.0
        return self.nodes / self.elapsed

    def pv_moves(self) -> List[Tuple[int, int]]:
        return [divmod(index, self.size) for index in self.pv]


_PRIORITY_CACHE: Dict[int, Tuple[int, ...]] = {}


def square_priority(size: int) -> Tuple[int, ...]:
    """Static move-ordering values for every square on a *size* board."""

    cached = _PRIORITY_CACHE.get(size)
    if cached is not None:
        return cached

    centre = (size - 1) / 2.0
    table: List[int] = []
    for row in range(size):
        for col in range(size):
            edge_row = row in (0, size - 1)
            edge_col = col in (0, size - 1)
            if edge_row and edge_col:
                value = 4000
            elif (row in (1, size - 2)) and (col in (1, size - 2)):
                value = -1200
            elif edge_row or edge_col:
                near_corner = (row in (0, size - 1) and col in (1, size - 2)) or (
                    col in (0, size - 1) and row in (1, size - 2)
                )
                value = -300 if near_corner else 320
            else:
                distance = abs(row - centre) + abs(col - centre)
                value = 60 - int(distance * 8)
            table.append(value)
    result = tuple(table)
    _PRIORITY_CACHE[size] = result
    return result


class Searcher:
    """Reusable alpha-beta searcher bound to one board size."""

    def __init__(
        self,
        size: int = DEFAULT_BOARD_SIZE,
        table_limit: int = 600_000,
        seed: Optional[int] = None,
    ) -> None:
        self.size = size
        self.geometry: Geometry = geometry_for(size)
        self.table_limit = table_limit
        self.priority = square_priority(size)
        self.tt: Dict[int, Tuple[int, int, int, int]] = {}
        self.nodes = 0
        self._deadline = float("inf")
        self._cancelled = False
        self._node_limit = 0
        self._history: Dict[int, int] = {}
        self._killers: List[List[int]] = []
        self._exact_empties = 0
        self._extend_empties = 0
        self._exact_mode = False
        self._partial_index = -1
        self._partial_score = -INF
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Drop the transposition table and heuristics (new game)."""

        self.tt.clear()
        self._history.clear()
        self._killers.clear()

    def cancel(self) -> None:
        self._cancelled = True

    def search(
        self,
        position: Position,
        limits: SearchLimits,
        progress: Optional[ProgressCallback] = None,
    ) -> SearchResult:
        """Search *position* and return the best move found.

        Iterative deepening always produces a usable move; if the root has few
        enough empty squares, the remaining budget is then spent trying to solve
        the game exactly, and a completed solve replaces the heuristic result.
        """

        started = time.perf_counter()
        self.nodes = 0
        self._cancelled = False
        self._node_limit = limits.node_limit
        self._exact_empties = limits.endgame_empties
        # In-tree extensions stay cheap so a shallow iteration always finishes.
        self._extend_empties = min(_IN_TREE_EXACT, limits.endgame_empties)
        self._exact_mode = False
        self._killers = [
            [-1, -1] for _ in range(max(8, position.size * position.size + 2))
        ]
        if limits.time_limit > 0:
            self._deadline = started + limits.time_limit
        else:
            self._deadline = float("inf")

        root_moves = position.legal_moves()
        if not root_moves:
            return SearchResult(
                index=None,
                size=position.size,
                nodes=0,
                elapsed=time.perf_counter() - started,
            )

        ordered = self._order(position, root_moves, -1, 0)
        best_index = ordered[0]
        best_score = 0
        best_depth = 0
        best_pv: List[int] = [best_index]
        complete = False
        self._partial_index = ordered[0]
        self._partial_score = -INF

        max_depth = max(1, min(limits.max_depth, position.empty_count()))
        for depth in range(1, max_depth + 1):
            try:
                score, index = self._root(
                    position, depth, best_score if best_depth else None, limits.noise
                )
            except SearchTimeout:
                # Keep whatever the aborted iteration had already established.
                if best_depth == 0 and self._partial_score > -INF:
                    best_index = self._partial_index
                    best_score = self._partial_score
                    best_depth = 1
                break

            best_index, best_score, best_depth = index, score, depth
            best_pv = self._extract_pv(position, depth)
            complete = True

            self._remember_result(
                SearchResult(
                    index=best_index,
                    size=position.size,
                    score=best_score,
                    depth=best_depth,
                    nodes=self.nodes,
                    elapsed=time.perf_counter() - started,
                    pv=best_pv,
                    complete=False,
                ),
                progress,
            )

            if abs(best_score) >= WIN_THRESHOLD:
                break
            if self._time_fraction(started) > 0.55:
                break

        empties = position.empty_count()
        if (
            limits.time_limit > 0
            and empties <= limits.endgame_empties
            and not self._cancelled
            and time.perf_counter() < self._deadline
        ):
            self._exact_mode = True
            try:
                score, index = self._search_root(position, empties + 1, -INF, INF, 0)
                best_index, best_score = index, score
                best_depth = empties
                best_pv = self._extract_pv(position, empties)
                complete = True
            except SearchTimeout:
                pass
            finally:
                self._exact_mode = False

        elapsed = time.perf_counter() - started
        return SearchResult(
            index=best_index,
            size=position.size,
            score=best_score,
            depth=best_depth,
            nodes=self.nodes,
            elapsed=elapsed,
            pv=best_pv,
            complete=complete,
        )

    def rank(self, position: Position, depth: int = 3) -> List[Tuple[int, int]]:
        """Score every legal move at a fixed depth, best first.

        Used by the opening-book generator and by game review.  Returns a list
        of ``(square_index, score)`` pairs from the mover's perspective.
        """

        self.nodes = 0
        self._cancelled = False
        self._deadline = float("inf")
        self._node_limit = 0
        self._exact_empties = min(8, max(0, position.empty_count() - depth))
        self._extend_empties = min(_IN_TREE_EXACT, self._exact_empties)
        self._exact_mode = False
        self._killers = [
            [-1, -1] for _ in range(max(8, position.size * position.size + 2))
        ]

        ranked: List[Tuple[int, int]] = []
        for index in iter_bits(position.legal_moves()):
            child = position.apply_index(index)
            score = -self._negamax(child, max(0, depth - 1), -INF, INF, 1)
            ranked.append((index, score))
        ranked.sort(key=lambda item: -item[1])
        return ranked

    def hint(
        self,
        position: Position,
        time_limit: float = 0.35,
        endgame_empties: int = 8,
    ) -> Optional[Tuple[int, int]]:
        """Quick analysis used by the hint button and move ratings."""

        result = self.search(
            position,
            SearchLimits(time_limit=time_limit, endgame_empties=endgame_empties),
        )
        return result.move

    # ------------------------------------------------------------------
    # Root
    # ------------------------------------------------------------------

    def _root(
        self,
        position: Position,
        depth: int,
        previous: Optional[int],
        noise: int,
    ) -> Tuple[int, int]:
        alpha, beta = -INF, INF
        if previous is not None and depth >= 4:
            window = 60
            alpha = previous - window
            beta = previous + window

        while True:
            score, index = self._search_root(position, depth, alpha, beta, noise)
            if score <= alpha and alpha > -INF:
                alpha = -INF
                continue
            if score >= beta and beta < INF:
                beta = INF
                continue
            return score, index

    def _search_root(
        self,
        position: Position,
        depth: int,
        alpha: int,
        beta: int,
        noise: int,
    ) -> Tuple[int, int]:
        moves = position.legal_moves()
        ordered = self._order(position, moves, self._tt_move(position), 0)
        best_index = ordered[0]
        best_score = -INF
        alpha_original = alpha

        for order, index in enumerate(ordered):
            if self._cancelled:
                raise SearchTimeout
            child = position.apply_index(index)
            if order == 0:
                score = -self._negamax(child, depth - 1, -beta, -alpha, 1)
            else:
                score = -self._negamax(child, depth - 1, -alpha - 1, -alpha, 1)
                if alpha < score < beta:
                    score = -self._negamax(child, depth - 1, -beta, -alpha, 1)

            if noise:
                score += self._rng.randint(-noise, noise)

            if score > best_score:
                best_score = score
                best_index = index
                if score > self._partial_score:
                    self._partial_score = score
                    self._partial_index = index
            alpha = max(alpha, score)
            if alpha >= beta:
                break

        if best_score <= alpha_original:
            flag = UPPER
        elif best_score >= beta:
            flag = LOWER
        else:
            flag = EXACT
        self._store(position.zobrist, depth, best_score, flag, best_index)
        return best_score, best_index

    # ------------------------------------------------------------------
    # Negamax
    # ------------------------------------------------------------------

    def _negamax(
        self,
        position: Position,
        depth: int,
        alpha: int,
        beta: int,
        ply: int,
    ) -> int:
        self.nodes += 1
        if (self.nodes & 2047) == 0:
            self._check_time()
        if self._node_limit and self.nodes >= self._node_limit:
            raise SearchTimeout

        key = position.zobrist
        entry = self.tt.get(key)
        tt_move = -1
        if entry is not None:
            entry_depth, entry_score, flag, entry_move = entry
            tt_move = entry_move
            if entry_depth >= depth:
                if flag == EXACT:
                    return entry_score
                if flag == LOWER:
                    alpha = max(alpha, entry_score)
                elif flag == UPPER:
                    beta = min(beta, entry_score)
                if alpha >= beta:
                    return entry_score

        moves = position.legal_moves()
        if not moves:
            other_moves = self.geometry.move_mask(position.other, position.own)
            if not other_moves:
                return terminal_score(
                    position.own.bit_count(), position.other.bit_count()
                )
            return -self._negamax(position.pass_turn(), depth, -beta, -alpha, ply)

        empties = position.empty_count()
        if depth <= 0:
            if self._exact_mode or empties <= self._extend_empties:
                depth = empties
            else:
                return evaluate(position, moves)

        alpha_original = alpha
        ordered = self._order(position, moves, tt_move, ply)
        best_score = -INF
        best_index = ordered[0]

        for order, index in enumerate(ordered):
            child = position.apply_index(index)
            if order == 0:
                score = -self._negamax(child, depth - 1, -beta, -alpha, ply + 1)
            else:
                score = -self._negamax(child, depth - 1, -alpha - 1, -alpha, ply + 1)
                if alpha < score < beta:
                    score = -self._negamax(child, depth - 1, -beta, -alpha, ply + 1)

            if score > best_score:
                best_score = score
                best_index = index
            alpha = max(alpha, score)
            if alpha >= beta:
                self._record_cutoff(index, ply, depth)
                break

        if best_score <= alpha_original:
            flag = UPPER
        elif best_score >= beta:
            flag = LOWER
        else:
            flag = EXACT
        self._store(key, depth, best_score, flag, best_index)
        return best_score

    # ------------------------------------------------------------------
    # Heuristics
    # ------------------------------------------------------------------

    def _order(
        self, position: Position, moves: int, tt_move: int, ply: int
    ) -> List[int]:
        priority = self.priority
        history = self._history
        killers = self._killers[ply] if 0 <= ply < len(self._killers) else (-1, -1)
        scored = []
        for index in iter_bits(moves):
            if index == tt_move:
                value = 1 << 20
            else:
                value = priority[index] + history.get(index, 0)
                if index == killers[0]:
                    value += 6000
                elif index == killers[1]:
                    value += 4000
            scored.append((value, index))
        scored.sort(reverse=True)
        return [index for _, index in scored]

    def _record_cutoff(self, index: int, ply: int, depth: int) -> None:
        if 0 <= ply < len(self._killers):
            slot = self._killers[ply]
            if index != slot[0]:
                slot[1] = slot[0]
                slot[0] = index
        self._history[index] = self._history.get(index, 0) + depth * depth

    def _store(self, key: int, depth: int, score: int, flag: int, index: int) -> None:
        if len(self.tt) >= self.table_limit:
            self.tt.clear()
        existing = self.tt.get(key)
        if existing is not None and existing[0] > depth:
            return
        self.tt[key] = (depth, score, flag, index)

    def _tt_move(self, position: Position) -> int:
        entry = self.tt.get(position.zobrist)
        return entry[3] if entry is not None else -1

    def _extract_pv(self, position: Position, depth: int) -> List[int]:
        pv: List[int] = []
        current = position
        for _ in range(depth):
            entry = self.tt.get(current.zobrist)
            if entry is None:
                break
            index = entry[3]
            if index < 0 or not (current.legal_moves() >> index) & 1:
                break
            pv.append(index)
            current = current.apply_index(index)
            current = (
                current.pass_turn()
                if not current.legal_moves() and not current.is_terminal()
                else current
            )
        return pv

    # ------------------------------------------------------------------
    # Time management
    # ------------------------------------------------------------------

    def _check_time(self) -> None:
        if self._cancelled or time.perf_counter() >= self._deadline:
            raise SearchTimeout

    def _time_fraction(self, started: float) -> float:
        total = self._deadline - started
        if total <= 0 or total == float("inf"):
            return 0.0
        return (time.perf_counter() - started) / total

    @staticmethod
    def _remember_result(
        result: SearchResult, progress: Optional[ProgressCallback]
    ) -> None:
        if progress is not None:
            progress(result)


__all__ = [
    "EXACT",
    "INF",
    "LOWER",
    "UPPER",
    "SearchLimits",
    "SearchResult",
    "SearchTimeout",
    "Searcher",
    "square_priority",
]
