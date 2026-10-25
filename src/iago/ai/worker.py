"""Background search worker.

Searching is CPU-bound and pure Python, so it runs on a worker thread.  Python's
GIL means the interface thread still gets scheduled regularly (the application
lowers the switch interval), which keeps animation and input alive while the
engine thinks.  The worker only publishes immutable result objects; it never
touches pygame.

Exactly one search runs at a time: starting a new one cancels and joins the
previous thread first, so the shared transposition table is never mutated from
two threads at once.
"""

from __future__ import annotations

import threading
from typing import Optional

from ..core.bitboard import Position
from ..core.board import Board
from ..util.log import get_logger
from .engine import Engine
from .search import SearchLimits, SearchResult

logger = get_logger("ai.worker")

BoardLike = Board | Position


class SearchWorker:
    """Run engine searches on a daemon thread and publish their results."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._engine: Optional[Engine] = None
        self._progress: Optional[SearchResult] = None
        self._result: Optional[SearchResult] = None
        self._token = 0
        self._running = False

    # ------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._running

    @property
    def progress(self) -> Optional[SearchResult]:
        with self._lock:
            return self._progress

    def start(
        self,
        engine: Engine,
        board: BoardLike,
        limits: SearchLimits,
    ) -> int:
        """Begin a search and return its token."""

        self.cancel()
        position = board.to_position() if isinstance(board, Board) else board

        with self._lock:
            self._token += 1
            token = self._token
            self._engine = engine
            self._progress = None
            self._result = None
            self._running = True

        def run() -> None:
            result: Optional[SearchResult] = None
            try:
                result = engine.analyse_limits(
                    position,
                    limits,
                    progress=lambda snapshot: self._publish(token, snapshot),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Background search failed: %s", exc)
                result = SearchResult(index=None, size=position.size)
            finally:
                with self._lock:
                    if self._token == token:
                        self._result = result
                        self._running = False

        thread = threading.Thread(target=run, name="iago-search", daemon=True)
        with self._lock:
            self._thread = thread
        thread.start()
        return token

    def _publish(self, token: int, snapshot: SearchResult) -> None:
        with self._lock:
            if self._token == token:
                self._progress = snapshot

    # ------------------------------------------------------------------

    def poll(self) -> tuple[Optional[SearchResult], Optional[SearchResult]]:
        """Return ``(latest_progress, final_result)`` without blocking."""

        with self._lock:
            return self._progress, self._result

    def cancel(self) -> None:
        """Abandon any in-flight search and wait briefly for the thread."""

        with self._lock:
            if not self._running and self._thread is None:
                return
            engine = self._engine
            thread = self._thread
            self._running = False
            self._token += 1
            self._thread = None
            self._result = None
            self._progress = None

        if engine is not None:
            engine.cancel_search()
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)

    def join(self, timeout: Optional[float] = None) -> None:
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def take_result(self) -> Optional[SearchResult]:
        """Return the final result once and clear it (and its progress)."""

        with self._lock:
            result = self._result
            self._result = None
            self._progress = None
            return result

    def reset(self) -> None:
        self.cancel()
        with self._lock:
            self._progress = None
            self._result = None


__all__ = ["SearchWorker"]
