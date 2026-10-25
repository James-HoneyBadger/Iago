"""Tests for the engine facade, difficulty presets and the opening book."""

from __future__ import annotations

import time

import pytest

from iago.ai import (
    DIFFICULTY_NAMES,
    LEVELS,
    MAX_DIFFICULTY,
    Engine,
    OpeningBook,
    get_level,
)
from iago.ai.evaluation import (
    evaluate,
    evaluate_for_black,
    terminal_score,
    win_probability,
)
from iago.ai.search import square_priority
from iago.core import Board, Position
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE

# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------


def test_level_table_is_contiguous_and_named():
    assert sorted(LEVELS) == list(range(1, MAX_DIFFICULTY + 1))
    assert DIFFICULTY_NAMES == tuple(
        LEVELS[i].name for i in range(1, MAX_DIFFICULTY + 1)
    )
    assert MAX_DIFFICULTY == 5


def test_levels_get_stronger():
    ordered = [LEVELS[i] for i in range(1, MAX_DIFFICULTY + 1)]
    budgets = [level.time_limit for level in ordered]
    assert budgets == sorted(budgets)
    assert ordered[0].is_random
    assert not ordered[-1].is_random


def test_get_level_clamps_out_of_range():
    assert get_level(0).number == 1
    assert get_level(99).number == MAX_DIFFICULTY


def test_engine_name_and_invalid_difficulty():
    for number, level in LEVELS.items():
        assert Engine(difficulty=number).name == level.name
    assert Engine(difficulty=99).name == "?"
    assert Engine(difficulty=99).level.number == MAX_DIFFICULTY


# ---------------------------------------------------------------------------
# Move generation through the engine
# ---------------------------------------------------------------------------


def test_easy_returns_a_legal_random_move():
    engine = Engine(difficulty=1, seed=1)
    board = Board()
    move = engine.get_move(board)
    assert move is not None
    assert board.is_valid_move(move[0], move[1], PLAYER_BLACK)


def test_easy_is_not_deterministic_across_games():
    board = Board()
    moves = {Engine(difficulty=1, seed=index).get_move(board) for index in range(12)}
    assert len(moves) > 1


def test_medium_is_instant():
    engine = Engine(difficulty=2)
    started = time.perf_counter()
    move = engine.get_move(Board())
    elapsed = time.perf_counter() - started
    assert move is not None
    assert elapsed < 0.25


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5])
def test_every_level_returns_a_legal_move(difficulty):
    board = Board()
    board.make_move(2, 3, PLAYER_BLACK)
    board.make_move(2, 4, PLAYER_WHITE)
    engine = Engine(difficulty=difficulty, seed=3)
    move = engine.get_move(board)
    assert move is not None
    assert board.is_valid_move(move[0], move[1], board.current_player)


def test_engine_returns_none_without_moves():
    board = Board()
    board.grid = [[PLAYER_BLACK] * 8 for _ in range(8)]
    board.current_player = PLAYER_WHITE
    engine = Engine(difficulty=3)
    assert engine.get_move(board) is None


def test_engine_accepts_a_position():
    engine = Engine(difficulty=1, seed=2)
    move = engine.get_move(Position())
    assert move in Position().legal_move_list()


def test_engine_rejects_unknown_board_types():
    with pytest.raises(TypeError):
        Engine().get_move("nope")  # type: ignore[arg-type]


def test_engine_resizes_for_a_position_of_another_size():
    """A 10x10 position must not crash an engine built for 8x8."""

    engine = Engine(difficulty=1, seed=4)
    assert engine.size == 8
    move = engine.get_move(Position(10))
    assert engine.size == 10
    assert move in Position(10).legal_move_list()


def test_engine_quick_hint_survives_a_size_change():
    engine = Engine(difficulty=2)
    hint = engine.quick_hint(Position(6))
    assert engine.size == 6
    assert hint in Position(6).legal_move_list()


def test_resize_switches_board_size():
    engine = Engine(difficulty=2)
    engine.resize(10)
    assert engine.size == 10
    move = engine.get_move(Position(10))
    assert move is not None
    assert move[0] < 10 and move[1] < 10


def test_hint_returns_a_legal_move():
    board = Board()
    engine = Engine(difficulty=4)
    hint = engine.get_hint(board, time_limit=0.1)
    assert hint is not None
    assert board.is_valid_move(hint[0], hint[1], PLAYER_BLACK)


def test_hint_without_moves_returns_none():
    board = Board()
    board.grid = [[PLAYER_BLACK] * 8 for _ in range(8)]
    board.current_player = PLAYER_WHITE
    assert Engine().get_hint(board, time_limit=0.05) is None


# ---------------------------------------------------------------------------
# Opening book
# ---------------------------------------------------------------------------


def test_book_loads_and_validates_lines():
    book = OpeningBook.load()
    assert not book.is_empty
    assert len(book.lines) >= 8
    for line in book.lines:
        board = Board()
        for index, (row, col) in enumerate(line.moves):
            player = PLAYER_BLACK if index % 2 == 0 else PLAYER_WHITE
            assert board.is_valid_move(
                row, col, player
            ), f"{line.name} contains illegal move {row},{col}"
            board.make_move(row, col, player)


def test_book_lookup_returns_a_continuation():
    book = OpeningBook.load()
    board = Board()
    board.make_move(2, 3, PLAYER_BLACK)  # d3
    move = book.lookup([(PLAYER_BLACK, 2, 3)])
    assert move is not None
    assert board.is_valid_move(move[0], move[1], PLAYER_WHITE)


def test_book_lookup_misses_on_unknown_prefix():
    assert OpeningBook.load().lookup([(PLAYER_BLACK, 0, 0)]) is None


def test_book_names_are_unique_per_prefix():
    book = OpeningBook.load()
    assert book.name_for([(PLAYER_BLACK, 2, 3)]) is not None


def test_book_survives_a_missing_file(tmp_path):
    book = OpeningBook.load(path=tmp_path / "nope.json")
    assert book.is_empty
    assert book.lookup([]) is None


def test_book_skips_illegal_lines(tmp_path):
    bad = tmp_path / "book.json"
    bad.write_text(
        '{"lines": [{"name": "Broken", "moves": ["a1", "a2"]}]}', encoding="utf-8"
    )
    book = OpeningBook.load(path=bad)
    assert book.is_empty


def test_engine_uses_the_book_within_its_first_moves():
    engine = Engine(difficulty=4)
    board = Board()
    board.make_move(2, 3, PLAYER_BLACK)
    engine.record_move(PLAYER_BLACK, 2, 3)
    expected = engine.book.lookup([(PLAYER_BLACK, 2, 3)])
    assert engine.get_move(board) == expected


def test_engine_opening_name_after_book_moves():
    engine = Engine(difficulty=4)
    board = Board()
    for player, row, col in (
        (PLAYER_BLACK, 2, 3),
        (PLAYER_WHITE, 2, 4),
    ):
        engine.record_move(player, row, col)
        board.make_move(row, col, player)
    assert engine.opening_name() is not None


def test_reset_log_clears_history():
    engine = Engine()
    engine.record_move(PLAYER_BLACK, 2, 3)
    assert engine.move_log
    engine.reset_log()
    assert not engine.move_log


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def test_evaluation_is_zero_for_the_symmetric_start():
    position = Position()
    assert abs(evaluate(position)) < 200


def test_evaluation_from_black_is_turn_independent():
    position = Position().apply(2, 3)
    assert evaluate_for_black(position) == evaluate_for_black(position.pass_turn())
    assert evaluate_for_black(position) == -evaluate(position)


def test_terminal_score_rewards_the_winner():
    assert terminal_score(10, 2) > 0
    assert terminal_score(2, 10) < 0
    assert terminal_score(5, 5) == 0
    assert terminal_score(10, 2) > terminal_score(3, 2)


def test_win_probability_bounds_and_direction():
    start = win_probability(Position())
    assert 0.0 <= start <= 1.0
    assert abs(start - 0.5) < 0.1

    full_black = Position.from_grid([[PLAYER_BLACK] * 8 for _ in range(8)])
    assert win_probability(full_black) == 1.0

    full_white = Position.from_grid([[PLAYER_WHITE] * 8 for _ in range(8)])
    assert win_probability(full_white) == 0.0


def test_square_priority_ranks_corners_first():
    table = square_priority(8)
    assert table[0] == table[7] == table[56] == table[63]
    assert table[0] > table[9]  # corner better than an X-square
    assert table[0] > table[27]  # corner better than the centre
