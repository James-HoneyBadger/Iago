"""Post-game review.

Each played move is compared with the engine's best alternative at a fixed
depth, then classified.  The whole review runs on a background thread in the
interface so the game-over screen stays responsive.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..ai.search import Searcher
from ..core.board import Board
from ..core.constants import DEFAULT_BOARD_SIZE, PLAYER_BLACK, PLAYER_WHITE
from ..core.notation import move_name
from ..util.log import get_logger

logger = get_logger("app.analysis")

Move = Tuple[int, int, int]

BEST = "Best"
GOOD = "Good"
INACCURACY = "Inaccuracy"
MISTAKE = "Mistake"
BLUNDER = "Blunder"

LABEL_ORDER = (BEST, GOOD, INACCURACY, MISTAKE, BLUNDER)

#: Search depth used for move ratings.  Depth 4 costs roughly two seconds for a
#: 60-move game on one core, which is cheap enough to run on a background thread
#: after every game while giving noticeably better labels than depth 2.
REVIEW_DEPTH = 4


#: Score (in engine units) at which a position is considered clearly winning.
_PROBABILITY_SCALE = 600.0
_MAX_SCORE = 5000


def win_probability_from_score(score: int) -> float:
    """Map an engine score onto a 0..1 winning probability."""

    bounded = max(-_MAX_SCORE, min(_MAX_SCORE, score))
    return 1.0 / (1.0 + math.exp(-bounded / _PROBABILITY_SCALE))


def classify(loss: float) -> str:
    """Classify a move by how many winning percentage points it gave away.

    Working in probability space keeps endgame scores (which are exact disc
    differences) comparable with mid-game heuristic scores.
    """

    if loss <= 0.5:
        return BEST
    if loss <= 2.0:
        return GOOD
    if loss <= 5.0:
        return INACCURACY
    if loss <= 12.0:
        return MISTAKE
    return BLUNDER


@dataclass(frozen=True)
class MoveAssessment:
    ply: int
    player: int
    row: int
    col: int
    best_row: int
    best_col: int
    loss: float
    label: str
    score: int

    @property
    def move_name(self) -> str:
        return move_name(self.row, self.col)

    @property
    def best_move_name(self) -> str:
        return move_name(self.best_row, self.best_col)


@dataclass
class GameReview:
    """The result of analysing a complete game."""

    board_size: int = DEFAULT_BOARD_SIZE
    assessments: List[MoveAssessment] = field(default_factory=list)
    engine_depth: int = REVIEW_DEPTH

    def accuracy(self, player: int) -> float:
        moves = [item for item in self.assessments if item.player == player]
        if not moves:
            return 0.0
        total = sum(item.loss for item in moves)
        average = total / len(moves)
        return max(0.0, 100.0 * math.exp(-average / 25.0))

    def counts(self, player: int) -> Dict[str, int]:
        counts = {label: 0 for label in LABEL_ORDER}
        for item in self.assessments:
            if item.player == player:
                counts[item.label] += 1
        return counts

    def worst(
        self, player: Optional[int] = None, limit: int = 5
    ) -> List[MoveAssessment]:
        items = [
            item
            for item in self.assessments
            if (player is None or item.player == player)
            and item.label in (MISTAKE, BLUNDER)
        ]
        items.sort(key=lambda item: -item.loss)
        return items[:limit]

    def assessment_for(self, ply: int) -> Optional[MoveAssessment]:
        for item in self.assessments:
            if item.ply == ply:
                return item
        return None

    def summary(self) -> str:
        black = self.counts(PLAYER_BLACK)
        white = self.counts(PLAYER_WHITE)
        return (
            f"Accuracy  Black {self.accuracy(PLAYER_BLACK):.0f}%  "
            f"White {self.accuracy(PLAYER_WHITE):.0f}%   "
            f"Blunders {black[BLUNDER]}/{white[BLUNDER]}"
        )


ProgressCallback = Callable[[int, int], None]


def analyse_moves(
    moves: Sequence[Move],
    size: int = DEFAULT_BOARD_SIZE,
    depth: int = REVIEW_DEPTH,
    progress: Optional[ProgressCallback] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> GameReview:
    """Analyse *moves* and return per-move assessments."""

    board = Board(size)
    searcher = Searcher(size, seed=0)
    review = GameReview(board_size=size, engine_depth=depth)
    total = len(moves)

    for index, (player, row, col) in enumerate(moves):
        if should_stop is not None and should_stop():
            break
        if not board.is_valid_move(row, col, player):
            logger.warning(
                "Skipping illegal move %s at ply %d", move_name(row, col), index + 1
            )
            continue
        position = board.to_position()
        ranked = searcher.rank(position, depth)
        played_index = row * size + col
        played_score = next(
            (score for square, score in ranked if square == played_index), None
        )
        if played_score is None:
            played_score = ranked[-1][1] if ranked else 0
        best_index, best_score = ranked[0] if ranked else (played_index, played_score)
        loss = (
            abs(
                win_probability_from_score(best_score)
                - win_probability_from_score(played_score)
            )
            * 100.0
        )
        best_row, best_col = divmod(best_index, size)
        review.assessments.append(
            MoveAssessment(
                ply=index + 1,
                player=player,
                row=row,
                col=col,
                best_row=best_row,
                best_col=best_col,
                loss=loss,
                label=classify(loss),
                score=played_score,
            )
        )
        board.make_move(row, col, player)
        board.check_game_over()
        if progress is not None:
            progress(index + 1, total)
    return review


class ReviewWorker:
    """Run :func:`analyse_moves` on a daemon thread."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._progress = (0, 0)
        self._review: Optional[GameReview] = None
        self._stop = threading.Event()

    @property
    def busy(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def progress(self) -> Tuple[int, int]:
        with self._lock:
            return self._progress

    def start(
        self,
        moves: Sequence[Move],
        size: int = DEFAULT_BOARD_SIZE,
        depth: int = REVIEW_DEPTH,
    ) -> None:
        self.cancel()
        self._stop = threading.Event()
        stop = self._stop
        with self._lock:
            self._review = None
            self._progress = (0, len(moves))

        def run() -> None:
            try:
                review = analyse_moves(
                    moves,
                    size,
                    depth,
                    progress=self._publish,
                    should_stop=stop.is_set,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Game review failed: %s", exc)
                review = GameReview(board_size=size, engine_depth=depth)
            with self._lock:
                if not stop.is_set():
                    self._review = review

        self._thread = threading.Thread(target=run, name="iago-review", daemon=True)
        self._thread.start()

    def _publish(self, done: int, total: int) -> None:
        with self._lock:
            self._progress = (done, total)

    def poll(self) -> Tuple[Tuple[int, int], Optional[GameReview]]:
        with self._lock:
            return self._progress, self._review

    def cancel(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.3)
        self._thread = None

    def take(self) -> Optional[GameReview]:
        with self._lock:
            review = self._review
            self._review = None
            return review


__all__ = [
    "BEST",
    "REVIEW_DEPTH",
    "BLUNDER",
    "GOOD",
    "INACCURACY",
    "LABEL_ORDER",
    "MISTAKE",
    "GameReview",
    "MoveAssessment",
    "ReviewWorker",
    "analyse_moves",
    "classify",
    "win_probability_from_score",
]
