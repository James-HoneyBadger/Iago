"""Game session state.

`Session` owns the board, the move history, undo/redo snapshots and the optional
clock.  It contains no pygame code, which makes the whole game model testable
and keeps the controller focused on input and rendering.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..ai.evaluation import win_probability
from ..ai.levels import MAX_DIFFICULTY, get_level
from ..core.board import Board
from ..core.constants import (
    DEFAULT_BOARD_SIZE,
    MODE_AVA,
    MODE_HVAI,
    MODE_HVH,
    PLAYER_BLACK,
    PLAYER_WHITE,
    opponent,
)
from ..core.notation import identify_opening, move_name
from ..util.errors import IllegalMoveError

Coordinate = Tuple[int, int]


@dataclass(frozen=True)
class MoveRecord:
    """One played move with the information the interface needs."""

    player: int
    row: int
    col: int
    flips: Tuple[Coordinate, ...]
    ply: int
    black_score: int
    white_score: int
    probability_black: float
    elapsed: float
    passed_next: bool = False

    @property
    def notation(self) -> str:
        return move_name(self.row, self.col)

    @property
    def coordinate(self) -> Coordinate:
        return self.row, self.col


@dataclass
class Snapshot:
    """Everything needed to restore the state before a move."""

    grid: List[List[int]]
    current_player: int
    game_over: bool
    winner: Optional[int]
    last_move: Optional[Coordinate]
    record_count: int
    elapsed: float
    finished_at: Optional[float]
    lowest_probability: float
    clock_elapsed: Dict[int, float]
    clock_moves: Dict[int, int]


@dataclass
class ClockState:
    """Per-player clocks.

    ``mode`` is ``"off"``, ``"stopwatch"`` (counts up) or ``"blitz"`` (counts
    down from ``base`` with an ``increment`` per move).
    """

    mode: str = "off"
    base: float = 300.0
    increment: float = 3.0
    elapsed: Dict[int, float] = field(default_factory=lambda: {1: 0.0, 2: 0.0})
    moves: Dict[int, int] = field(default_factory=lambda: {1: 0, 2: 0})
    running: Optional[int] = None
    since: float = 0.0

    def start(self, player: int, now: float) -> None:
        self.running = player
        self.since = now

    def stop(self, now: float) -> None:
        if self.running is None:
            return
        self.elapsed[self.running] = self.elapsed_for(self.running, now)
        self.running = None

    def elapsed_for(self, player: int, now: float) -> float:
        total = self.elapsed.get(player, 0.0)
        if self.running == player:
            total += max(0.0, now - self.since)
        return total

    def remaining(self, player: int, now: float) -> Optional[float]:
        if self.mode != "blitz":
            return None
        remaining = self.base - self.elapsed_for(player, now)
        remaining += self.increment * self.moves.get(player, 0)
        return max(0.0, remaining)

    def flagged(self, now: float) -> Optional[int]:
        if self.mode != "blitz":
            return None
        for player in (PLAYER_BLACK, PLAYER_WHITE):
            remaining = self.remaining(player, now)
            if remaining is not None and remaining <= 0.0:
                return player
        return None

    def snapshot(self) -> Dict[int, float]:
        return dict(self.elapsed)

    def restore(self, elapsed: Dict[int, float]) -> None:
        self.elapsed = dict(elapsed)
        self.running = None

    def reset(self) -> None:
        self.elapsed = {PLAYER_BLACK: 0.0, PLAYER_WHITE: 0.0}
        self.moves = {PLAYER_BLACK: 0, PLAYER_WHITE: 0}
        self.running = None
        self.since = 0.0


class Session:
    """The complete state of one game."""

    def __init__(
        self,
        size: int = DEFAULT_BOARD_SIZE,
        mode: str = MODE_HVAI,
        player_color: int = PLAYER_BLACK,
        level: int = 3,
    ) -> None:
        self.size = size
        self.mode = mode
        self.player_color = player_color
        self.level = max(1, min(MAX_DIFFICULTY, level))
        self.board = Board(size)
        self.records: List[MoveRecord] = []
        self.redo_records: List[MoveRecord] = []
        self._snapshots: List[Snapshot] = []
        self._redo_snapshots: List[Snapshot] = []
        self.clock = ClockState()
        self.started_at = time.monotonic()
        self.finished_at: Optional[float] = None
        self.last_move: Optional[Coordinate] = None
        self.lowest_probability = 0.5
        self.pass_happened = False
        self.opening_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def ai_color(self) -> int:
        return opponent(self.player_color)

    @property
    def current_player(self) -> int:
        return self.board.current_player

    @property
    def game_over(self) -> bool:
        return self.board.game_over

    @property
    def winner(self) -> Optional[int]:
        return self.board.winner

    @property
    def ply(self) -> int:
        return len(self.records)

    @property
    def move_count(self) -> int:
        return len(self.records)

    def level_name(self) -> str:
        return get_level(self.level).name

    def is_human_turn(self) -> bool:
        if self.game_over:
            return False
        if self.mode == MODE_HVH:
            return True
        if self.mode == MODE_AVA:
            return False
        return self.current_player == self.player_color

    def is_human_player(self, player: int) -> bool:
        if self.mode == MODE_HVH:
            return True
        if self.mode == MODE_AVA:
            return False
        return player == self.player_color

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        size: Optional[int] = None,
        mode: Optional[str] = None,
        player_color: Optional[int] = None,
        level: Optional[int] = None,
        clock_mode: Optional[str] = None,
        blitz_base: float = 300.0,
        increment: float = 3.0,
    ) -> None:
        if size is not None and size != self.size:
            self.size = size
            self.board = Board(size)
        else:
            self.board.reset()
        if mode is not None:
            self.mode = mode
        if player_color is not None:
            self.player_color = player_color
        if level is not None:
            self.level = max(1, min(MAX_DIFFICULTY, level))
        if clock_mode is not None:
            self.clock.mode = clock_mode
        if self.clock.mode == "blitz":
            self.clock.base = blitz_base
            self.clock.increment = increment
        self.clock.reset()

        self.records.clear()
        self.redo_records.clear()
        self._snapshots.clear()
        self._redo_snapshots.clear()
        self.last_move = None
        self.lowest_probability = 0.5
        self.started_at = time.monotonic()
        self.finished_at = None
        self.pass_happened = False
        self.opening_name = None

    # ------------------------------------------------------------------
    # Playing
    # ------------------------------------------------------------------

    def legal_moves(self, player: Optional[int] = None) -> List[Coordinate]:
        return self.board.get_valid_moves(player or self.current_player)

    def is_legal(self, row: int, col: int) -> bool:
        return self.board.is_valid_move(row, col, self.current_player)

    def apply_move(self, row: int, col: int, now: Optional[float] = None) -> MoveRecord:
        """Play a move for the side to move and return its record."""

        player = self.current_player
        if not self.board.is_valid_move(row, col, player):
            raise IllegalMoveError(
                f"{move_name(row, col)} is not a legal move for player {player}"
            )
        now = time.monotonic() if now is None else now
        snapshot = self._snapshot(now)

        flips = self.board.make_move(row, col, player)
        self.board.check_game_over()

        probability = win_probability(self.board.to_position())
        self.lowest_probability = min(self.lowest_probability, probability)
        passed = not self.board.game_over and self.board.current_player == player
        record = MoveRecord(
            player=player,
            row=row,
            col=col,
            flips=tuple(flips),
            ply=len(self.records) + 1,
            black_score=self.board.get_score()[0],
            white_score=self.board.get_score()[1],
            probability_black=probability,
            elapsed=now - self.started_at,
            passed_next=passed,
        )
        self.records.append(record)
        self._snapshots.append(snapshot)
        self.redo_records.clear()
        self._redo_snapshots.clear()
        self.last_move = (row, col)
        self.pass_happened = passed
        opening = identify_opening(self.to_move_log(), self.size)
        self.opening_name = opening.name if opening is not None else None
        self.clock.moves[player] = self.clock.moves.get(player, 0) + 1
        self.clock.stop(now)
        if self.board.game_over:
            self.finished_at = now
        else:
            self.clock.start(self.current_player, now)
        return record

    def play_pending_pass(self, now: Optional[float] = None) -> bool:
        """Pass the turn when the side to move has no legal move.

        Returns True when a pass was applied.
        """

        if self.board.game_over:
            return False
        if self.legal_moves():
            return False
        now = time.monotonic() if now is None else now
        self.board.check_game_over()
        self.pass_happened = True
        if not self.board.game_over:
            self.clock.stop(now)
            self.clock.start(self.current_player, now)
        return True

    def finish_on_time(self, now: Optional[float] = None) -> Optional[int]:
        """End the game when a clock runs out; returns the losing player."""

        now = time.monotonic() if now is None else now
        flagged = self.clock.flagged(now)
        if flagged is None:
            return None
        self.clock.stop(now)
        self.board.game_over = True
        self.board.winner = opponent(flagged)
        self.finished_at = now
        return flagged

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------

    def undo(self) -> bool:
        """Step back one move. Returns False when there is nothing to undo."""

        if not self._snapshots:
            return False
        now = time.monotonic()
        self._redo_snapshots.append(self._snapshot(now))
        self.redo_records.append(self.records.pop())
        self._restore(self._snapshots.pop())
        return True

    def redo(self) -> bool:
        """Replay a previously undone move."""

        if not self._redo_snapshots:
            return False
        now = time.monotonic()
        self._snapshots.append(self._snapshot(now))
        record = self.redo_records.pop()
        self.records.append(record)
        self._restore(self._redo_snapshots.pop())
        self.last_move = record.coordinate
        return True

    def can_undo(self) -> bool:
        return bool(self._snapshots)

    def can_redo(self) -> bool:
        return bool(self._redo_snapshots)

    def _snapshot(self, now: float) -> Snapshot:
        return Snapshot(
            grid=[row[:] for row in self.board.grid],
            current_player=self.board.current_player,
            game_over=self.board.game_over,
            winner=self.board.winner,
            last_move=self.last_move,
            record_count=len(self.records),
            elapsed=now - self.started_at,
            finished_at=self.finished_at,
            lowest_probability=self.lowest_probability,
            clock_elapsed=self.clock.snapshot(),
            clock_moves=dict(self.clock.moves),
        )

    def _restore(self, snapshot: Snapshot) -> None:
        self.board.grid = [row[:] for row in snapshot.grid]
        self.board.current_player = snapshot.current_player
        self.board.game_over = snapshot.game_over
        self.board.winner = snapshot.winner
        self.last_move = snapshot.last_move
        self.lowest_probability = snapshot.lowest_probability
        self.clock.restore(snapshot.clock_elapsed)
        self.clock.moves = dict(snapshot.clock_moves)
        self.finished_at = snapshot.finished_at
        self.pass_happened = False

    # ------------------------------------------------------------------
    # Replay and serialisation
    # ------------------------------------------------------------------

    def position_at(self, ply: int) -> Board:
        """Return the board after *ply* moves (0 = initial position)."""

        board = Board(self.size)
        for player, row, col in self.to_move_log()[:ply]:
            if not board.is_valid_move(row, col, player):
                break
            board.make_move(row, col, player)
            board.check_game_over()
        return board

    def to_move_log(self) -> List[Tuple[int, int, int]]:
        return [(record.player, record.row, record.col) for record in self.records]

    def load_move_log(self, moves: List[Tuple[int, int, int]]) -> None:
        """Rebuild the session from a move log (used when loading a save)."""

        self.board = Board(self.size)
        self.records.clear()
        self._snapshots.clear()
        self.redo_records.clear()
        self._redo_snapshots.clear()
        self.last_move = None
        now = time.monotonic()
        for player, row, col in moves:
            if self.board.current_player != player:
                raise IllegalMoveError(
                    f"Move log out of sync: expected player "
                    f"{self.board.current_player}, found {player}"
                )
            self.apply_move(row, col, now)

    def score(self) -> Tuple[int, int]:
        return self.board.get_score()

    def elapsed(self, now: Optional[float] = None) -> float:
        now = time.monotonic() if now is None else now
        return (self.finished_at or now) - self.started_at

    def player_score(self, player: int) -> int:
        black, white = self.score()
        return black if player == PLAYER_BLACK else white

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Session(mode={self.mode}, size={self.size}, plies={self.ply}, "
            f"turn={self.current_player})"
        )


__all__ = ["ClockState", "MoveRecord", "Session", "Snapshot"]
