"""Tests for the alpha-beta search, the endgame solver and the worker."""

from __future__ import annotations

import random
import threading
import time

import pytest

from iago.ai import (
    Engine,
    SearchLimits,
    SearchResult,
    Searcher,
    SearchWorker,
    perfect_difference,
    solve,
)
from iago.ai.evaluation import TERMINAL_BONUS
from iago.core import Position
from iago.core.bitboard import iter_bits


def random_position(seed: int, plies: int, size: int = 8) -> Position:
    rng = random.Random(seed)
    position = Position(size)
    for _ in range(plies):
        moves = position.legal_move_list()
        if not moves:
            position = position.pass_turn()
            continue
        position = position.apply(*rng.choice(moves))
    return position


def score_to_difference(score: int) -> int:
    """Convert an exact solver score back into a disc difference."""

    if score > 0:
        return (score - TERMINAL_BONUS) // 1000
    if score < 0:
        return (score + TERMINAL_BONUS) // 1000
    return 0


# ---------------------------------------------------------------------------
# Root behaviour
# ---------------------------------------------------------------------------


def test_search_returns_a_legal_move():
    position = random_position(1, 12)
    result = Searcher(8).search(position, SearchLimits(time_limit=0.3, max_depth=10))
    assert isinstance(result, SearchResult)
    assert result.move in position.legal_move_list()
    assert result.depth >= 1
    assert result.nodes > 0


def test_search_without_moves_returns_none():
    position = Position.from_grid([[1] * 8 for _ in range(8)]).with_turn(2)
    result = Searcher(8).search(position, SearchLimits(time_limit=0.1))
    assert result.move is None


def test_search_reports_principal_variation():
    position = random_position(2, 10)
    result = Searcher(8).search(position, SearchLimits(time_limit=0.4, max_depth=8))
    assert result.pv
    assert result.pv[0] == result.index
    assert len(result.pv) <= max(1, result.depth)


def test_search_respects_the_time_budget():
    position = random_position(3, 8)
    started = time.perf_counter()
    Searcher(8).search(position, SearchLimits(time_limit=0.15, max_depth=30))
    elapsed = time.perf_counter() - started
    assert elapsed < 1.5


def test_cancel_stops_a_search_promptly():
    position = random_position(4, 6)
    searcher = Searcher(8)
    outcome: dict[str, object] = {}

    def run() -> None:
        started = time.perf_counter()
        outcome["result"] = searcher.search(
            position, SearchLimits(time_limit=5.0, max_depth=40)
        )
        outcome["elapsed"] = time.perf_counter() - started

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(0.15)
    searcher.cancel()
    thread.join(timeout=3.0)
    assert not thread.is_alive()
    assert outcome["elapsed"] < 1.5
    result = outcome["result"]
    assert isinstance(result, SearchResult)
    assert result.depth == 0 or result.move in position.legal_move_list()


def test_rank_orders_moves_by_score():
    position = random_position(5, 14)
    ranked = Searcher(8).rank(position, depth=3)
    assert len(ranked) == len(position.legal_move_list())
    scores = [score for _, score in ranked]
    assert scores == sorted(scores, reverse=True)
    assert all(index in set(iter_bits(position.legal_moves())) for index, _ in ranked)


def test_fixed_depth_search_is_deterministic():
    position = random_position(6, 9)
    limits = SearchLimits(time_limit=0, max_depth=4)
    first = Searcher(8, seed=1).search(position, limits)
    second = Searcher(8, seed=1).search(position, limits)
    assert (first.index, first.score, first.pv) == (
        second.index,
        second.score,
        second.pv,
    )


def test_transposition_table_does_not_change_the_result():
    position = random_position(7, 11)
    limits = SearchLimits(time_limit=0, max_depth=4)
    with_table = Searcher(8, seed=2).search(position, limits)

    class NoTable(Searcher):
        def _store(self, *args, **kwargs):  # noqa: D102 - test double
            return

    without_table = NoTable(8, seed=2).search(position, limits)
    assert with_table.score == without_table.score


def test_clear_resets_the_table():
    searcher = Searcher(8)
    searcher.search(random_position(8, 6), SearchLimits(time_limit=0, max_depth=3))
    assert searcher.tt
    searcher.clear()
    assert not searcher.tt


def test_search_plays_a_perfect_endgame():
    position = random_position(31, 56)
    while position.empty_count() > 4:
        moves = position.legal_move_list()
        if not moves:
            position = position.pass_turn()
            continue
        position = position.apply(*moves[0])
    best = max(
        -perfect_difference(position.apply_index(index))
        for index in iter_bits(position.legal_moves())
    )
    result = Searcher(8).search(
        position, SearchLimits(time_limit=1.0, max_depth=20, endgame_empties=10)
    )
    assert score_to_difference(result.score) == best


# ---------------------------------------------------------------------------
# Endgame exactness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [11, 12, 13, 14])
def test_exact_solver_matches_brute_force(seed):
    position = random_position(seed, 52)
    while position.empty_count() > 6:
        moves = position.legal_move_list()
        if not moves:
            position = position.pass_turn()
            continue
        position = position.apply(*moves[0])
    expected = perfect_difference(position)
    result = solve(position, time_limit=10.0)
    assert score_to_difference(result.score) == expected
    assert result.move in position.legal_move_list()


def test_perfect_difference_on_a_full_board():
    grid = [[1] * 8 for _ in range(8)]
    assert perfect_difference(Position.from_grid(grid)) == 64


def test_perfect_difference_handles_passes():
    grid = [[0] * 8 for _ in range(8)]
    grid[0][0] = 2
    grid[0][1] = 1
    position = Position.from_grid(grid).with_turn(1)
    # Black has no move, White has none either in this contrived position.
    value = perfect_difference(position)
    assert isinstance(value, int)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def test_worker_returns_a_result():
    worker = SearchWorker()
    engine = Engine(difficulty=4)
    position = random_position(21, 20)
    worker.start(engine, position, SearchLimits(time_limit=0.2, max_depth=20))
    deadline = time.perf_counter() + 5.0
    result = None
    while time.perf_counter() < deadline:
        _, final = worker.poll()
        if final is not None:
            result = final
            break
        time.sleep(0.01)
    worker.join(1.0)
    assert result is not None
    assert result.move in position.legal_move_list()
    assert not worker.busy


def test_worker_cancel_clears_busy_state():
    worker = SearchWorker()
    engine = Engine(difficulty=5)
    worker.start(
        engine, random_position(22, 10), SearchLimits(time_limit=5.0, max_depth=40)
    )
    assert worker.busy
    worker.cancel()
    assert not worker.busy


def test_worker_reports_progress():
    worker = SearchWorker()
    engine = Engine(difficulty=5)
    worker.start(
        engine,
        random_position(23, 8),
        SearchLimits(time_limit=0.4, max_depth=30),
    )
    deadline = time.perf_counter() + 5.0
    saw_progress = False
    while time.perf_counter() < deadline:
        progress, final = worker.poll()
        if progress is not None and progress.depth >= 1:
            saw_progress = True
        if final is not None:
            break
        time.sleep(0.01)
    worker.join(1.0)
    assert saw_progress


def test_worker_take_result_clears_it():
    worker = SearchWorker()
    engine = Engine(difficulty=3)
    worker.start(engine, Position(), SearchLimits(time_limit=0.1, max_depth=3))
    worker.join(5.0)
    assert worker.take_result() is not None
    assert worker.take_result() is None
