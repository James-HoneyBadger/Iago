"""Tests for the session model: moves, undo/redo, clocks and replay."""

from __future__ import annotations

import time

import pytest

from iago.app.session import ClockState, Session
from iago.core.constants import (
    MODE_AVA,
    MODE_HVAI,
    MODE_HVH,
    PLAYER_BLACK,
    PLAYER_WHITE,
)
from iago.util.errors import IllegalMoveError


@pytest.fixture()
def session() -> Session:
    return Session(size=8, mode=MODE_HVAI, player_color=PLAYER_BLACK, level=2)


def test_initial_state(session):
    assert session.ply == 0
    assert session.current_player == PLAYER_BLACK
    assert not session.game_over
    assert session.is_human_turn()
    assert session.score() == (2, 2)
    assert session.level_name() == "Medium"


def test_apply_move_records_and_switches_turn(session):
    record = session.apply_move(2, 3)
    assert record.player == PLAYER_BLACK
    assert record.notation == "d3"
    assert record.flips == ((3, 3),)
    assert record.ply == 1
    assert 0.0 <= record.probability_black <= 1.0
    assert session.current_player == PLAYER_WHITE
    assert session.last_move == (2, 3)
    assert not session.is_human_turn()


def test_illegal_move_raises_and_does_not_mutate(session):
    with pytest.raises(IllegalMoveError):
        session.apply_move(0, 0)
    assert session.ply == 0
    assert session.current_player == PLAYER_BLACK


def test_scores_follow_the_board(session):
    session.apply_move(2, 3)
    assert session.score() == (4, 1)
    record = session.records[-1]
    assert (record.black_score, record.white_score) == (4, 1)


def test_undo_and_redo_restore_everything(session):
    session.apply_move(2, 3)
    session.apply_move(2, 4)
    before = [row[:] for row in session.board.grid]

    assert session.undo()
    assert session.ply == 1
    assert session.current_player == PLAYER_WHITE
    assert session.last_move == (2, 3)

    assert session.redo()
    assert session.ply == 2
    assert session.board.grid == before
    assert session.current_player == PLAYER_BLACK


def test_undo_all_the_way_to_the_start(session):
    session.apply_move(2, 3)
    session.apply_move(2, 4)
    assert session.undo()
    assert session.undo()
    assert not session.can_undo()
    assert session.ply == 0
    assert session.board.grid[3][3] == PLAYER_WHITE
    assert session.board.grid[3][4] == PLAYER_BLACK


def test_new_move_clears_redo(session):
    session.apply_move(2, 3)
    session.undo()
    assert session.can_redo()
    session.apply_move(3, 2)
    assert not session.can_redo()


def test_redo_without_history_is_false(session):
    assert session.redo() is False


def test_reset_clears_history_but_keeps_configuration(session):
    session.apply_move(2, 3)
    session.reset()
    assert session.ply == 0
    assert not session.can_undo()
    assert session.mode == MODE_HVAI
    assert session.size == 8
    assert session.score() == (2, 2)


def test_resize_creates_a_new_board(session):
    session.reset(size=10)
    assert session.size == 10
    assert len(session.board.grid) == 10
    assert len(session.legal_moves()) == 4


def test_human_turn_per_mode():
    hvai = Session(mode=MODE_HVAI, player_color=PLAYER_WHITE)
    assert not hvai.is_human_turn()
    assert hvai.is_human_player(PLAYER_WHITE)
    assert not hvai.is_human_player(PLAYER_BLACK)

    hvh = Session(mode=MODE_HVH)
    assert hvh.is_human_turn()
    assert hvh.is_human_player(PLAYER_BLACK)
    assert hvh.is_human_player(PLAYER_WHITE)

    ava = Session(mode=MODE_AVA)
    assert not ava.is_human_turn()


def test_level_is_clamped():
    assert Session(level=99).level == 5
    assert Session(level=0).level == 1


def test_position_at_replays_prefix(session):
    session.apply_move(2, 3)
    session.apply_move(2, 4)
    start = session.position_at(0)
    middle = session.position_at(1)
    end = session.position_at(2)
    assert start.grid[3][3] == PLAYER_WHITE
    assert middle.grid[2][3] == PLAYER_BLACK
    assert end.grid[2][3] == PLAYER_BLACK
    assert end.grid[2][4] == PLAYER_WHITE


def test_load_move_log_rebuilds_session(session):
    moves = [(PLAYER_BLACK, 2, 3), (PLAYER_WHITE, 2, 4), (PLAYER_BLACK, 4, 5)]
    session.load_move_log(moves)
    assert session.to_move_log() == moves
    assert session.ply == 3


def test_load_move_log_rejects_desync(session):
    with pytest.raises(IllegalMoveError):
        session.load_move_log([(PLAYER_WHITE, 2, 4)])


def test_pass_handling_detects_passed_turn(session):
    # Black plays d3, White plays e3, then Black has moves, so no pass yet.
    session.apply_move(2, 3)
    session.apply_move(2, 4)
    assert session.pass_happened is False
    assert not session.play_pending_pass()


def test_play_pending_pass_switches_player_when_stuck(session):
    session.board.grid = [[0] * 8 for _ in range(8)]
    session.board.grid[0][0] = PLAYER_WHITE
    session.board.grid[0][1] = PLAYER_BLACK
    session.board.grid[7][7] = PLAYER_WHITE
    session.board.current_player = PLAYER_BLACK
    assert session.play_pending_pass()
    assert session.current_player == PLAYER_WHITE


def test_elapsed_grows(session):
    start = session.elapsed()
    time.sleep(0.01)
    assert session.elapsed() > start


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------


def test_stopwatch_clock_accumulates():
    clock = ClockState(mode="stopwatch")
    clock.start(PLAYER_BLACK, 100.0)
    clock.stop(104.0)
    assert clock.elapsed_for(PLAYER_BLACK, 110.0) == pytest.approx(4.0)
    assert clock.remaining(PLAYER_BLACK, 110.0) is None


def test_blitz_clock_counts_down_and_flags():
    clock = ClockState(mode="blitz", base=10.0, increment=2.0)
    clock.start(PLAYER_BLACK, 0.0)
    assert clock.remaining(PLAYER_BLACK, 4.0) == pytest.approx(6.0)
    clock.stop(4.0)
    clock.moves[PLAYER_BLACK] = 1
    assert clock.remaining(PLAYER_BLACK, 4.0) == pytest.approx(8.0)
    assert clock.flagged(12.0) is None
    clock.elapsed[PLAYER_BLACK] = 100.0
    assert clock.flagged(12.0) == PLAYER_BLACK


def test_clock_snapshot_and_restore():
    clock = ClockState(mode="blitz")
    clock.start(PLAYER_BLACK, 0.0)
    clock.stop(5.0)
    snapshot = clock.snapshot()
    clock.reset()
    assert clock.elapsed_for(PLAYER_BLACK, 6.0) == 0.0
    clock.restore(snapshot)
    assert clock.elapsed_for(PLAYER_BLACK, 6.0) == pytest.approx(5.0)


def test_finish_on_time_sets_winner(session):
    session.clock.mode = "blitz"
    session.clock.base = 1.0
    session.clock.start(PLAYER_BLACK, 0.0)
    assert session.finish_on_time(5.0) == PLAYER_BLACK
    assert session.game_over
    assert session.winner == PLAYER_WHITE
