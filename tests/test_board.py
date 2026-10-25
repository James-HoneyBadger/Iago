"""Tests for the reference list-based rules."""

from __future__ import annotations

import pytest

from iago.core import Board, Position
from iago.core.constants import EMPTY, PLAYER_BLACK, PLAYER_WHITE

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def test_initial_board_layout():
    board = Board()
    assert board.grid[3][3] == PLAYER_WHITE
    assert board.grid[3][4] == PLAYER_BLACK
    assert board.grid[4][3] == PLAYER_BLACK
    assert board.grid[4][4] == PLAYER_WHITE
    assert board.get_score() == (2, 2)
    assert board.current_player == PLAYER_BLACK
    assert not board.game_over
    assert board.winner is None


def test_reset_clears_a_played_board():
    board = Board()
    board.make_move(2, 3, PLAYER_BLACK)
    board.make_move(2, 4, PLAYER_WHITE)
    board.game_over = True
    board.winner = PLAYER_BLACK
    board.reset()
    assert board.get_score() == (2, 2)
    assert board.current_player == PLAYER_BLACK
    assert not board.game_over
    assert board.winner is None


@pytest.mark.parametrize("size", [6, 8, 10])
def test_supported_sizes_reset_centred(size):
    board = Board(size)
    center = size // 2
    assert board.grid[center - 1][center - 1] == PLAYER_WHITE
    assert board.grid[center][center] == PLAYER_WHITE
    assert board.get_score() == (2, 2)
    assert len(board.get_valid_moves(PLAYER_BLACK)) == 4


def test_rejects_tiny_board():
    with pytest.raises(ValueError):
        Board(3)


# ---------------------------------------------------------------------------
# Move validity
# ---------------------------------------------------------------------------


def test_valid_moves_at_start():
    board = Board()
    assert set(board.get_valid_moves(PLAYER_BLACK)) == {
        (2, 3),
        (3, 2),
        (4, 5),
        (5, 4),
    }


def test_out_of_bounds_and_occupied_squares_are_invalid():
    board = Board()
    assert not board.is_valid_move(-1, 0, PLAYER_BLACK)
    assert not board.is_valid_move(0, 8, PLAYER_BLACK)
    assert not board.is_valid_move(3, 3, PLAYER_BLACK)


def test_move_that_flips_nothing_is_invalid():
    board = Board()
    assert not board.is_valid_move(0, 0, PLAYER_BLACK)


def test_would_flip_requires_bracketing_disc():
    board = Board()
    # d3 flips downwards towards the black disc on d4.
    assert board._would_flip(2, 3, 1, 0, PLAYER_BLACK)
    # ... but not upwards, where the square is empty.
    assert not board._would_flip(2, 3, -1, 0, PLAYER_BLACK)


def test_flip_direction_captures_cells():
    board = Board()
    flipped = board._flip_direction(2, 3, 1, 0, PLAYER_BLACK)
    assert flipped == [(3, 3)]
    assert board.grid[3][3] == PLAYER_BLACK


def test_flip_direction_returns_empty_when_blocked_by_empty_square():
    board = Board()
    assert board._flip_direction(0, 0, 1, 0, PLAYER_BLACK) == []


# ---------------------------------------------------------------------------
# Making moves
# ---------------------------------------------------------------------------


def test_make_move_flips_and_switches_turn():
    board = Board()
    flipped = board.make_move(2, 3, PLAYER_BLACK)  # d3 flips d4
    assert flipped == [(3, 3)]
    assert board.grid[3][3] == PLAYER_BLACK
    assert board.current_player == PLAYER_WHITE
    assert board.get_score() == (4, 1)


def test_make_move_flips_in_multiple_directions():
    board = Board()
    board.grid = [[EMPTY] * 8 for _ in range(8)]
    # A black move at c3 flips one disc to the right and one downwards.
    board.grid[2][3] = PLAYER_WHITE
    board.grid[2][4] = PLAYER_BLACK
    board.grid[3][2] = PLAYER_WHITE
    board.grid[4][2] = PLAYER_BLACK
    board.current_player = PLAYER_BLACK

    assert board.is_valid_move(2, 2, PLAYER_BLACK)
    flipped = board.make_move(2, 2, PLAYER_BLACK)
    assert set(flipped) == {(2, 3), (3, 2)}
    assert board.grid[2][3] == PLAYER_BLACK
    assert board.grid[3][2] == PLAYER_BLACK


def test_make_move_returns_empty_for_illegal_move_and_does_not_mutate():
    board = Board()
    before = [row[:] for row in board.grid]
    assert board.make_move(0, 0, PLAYER_BLACK) == []
    assert board.grid == before
    assert board.current_player == PLAYER_BLACK


def test_switch_player_toggles_both_ways():
    board = Board()
    board.switch_player()
    assert board.current_player == PLAYER_WHITE
    board.switch_player()
    assert board.current_player == PLAYER_BLACK


def test_get_flips_is_pure():
    board = Board()
    before = [row[:] for row in board.grid]
    flips = board.get_flips(2, 3, PLAYER_BLACK)
    assert flips == [(3, 3)]
    assert board.grid == before


def test_get_flips_matches_make_move():
    board = Board()
    expected = set(board.get_flips(2, 3, PLAYER_BLACK))
    actual = set(board.make_move(2, 3, PLAYER_BLACK))
    assert expected == actual


def test_get_flips_returns_empty_for_invalid_move():
    assert Board().get_flips(0, 0, PLAYER_BLACK) == []


# ---------------------------------------------------------------------------
# Scoring and termination
# ---------------------------------------------------------------------------


def test_score_counts_both_colours():
    board = Board()
    board.grid = [[EMPTY] * 8 for _ in range(8)]
    board.grid[0][0] = PLAYER_BLACK
    board.grid[7][7] = PLAYER_WHITE
    assert board.get_score() == (1, 1)
    assert board.empty_count() == 62


def test_check_game_over_sets_winner():
    board = Board()
    board.grid = [[PLAYER_BLACK] * 8 for _ in range(8)]
    assert board.check_game_over() is True
    assert board.game_over
    assert board.winner == PLAYER_BLACK

    board = Board()
    board.grid = [[PLAYER_WHITE] * 8 for _ in range(8)]
    board.check_game_over()
    assert board.winner == PLAYER_WHITE

    board = Board()
    board.grid = [
        [PLAYER_BLACK if (r + c) % 2 == 0 else PLAYER_WHITE for c in range(8)]
        for r in range(8)
    ]
    board.check_game_over()
    assert board.game_over
    assert board.winner == 0


def test_check_game_over_passes_turn_when_stuck():
    board = Board()
    board.grid = [[EMPTY] * 8 for _ in range(8)]
    board.grid[0][0] = PLAYER_WHITE
    board.grid[0][1] = PLAYER_BLACK
    board.grid[7][7] = PLAYER_WHITE
    board.current_player = PLAYER_BLACK
    assert board.check_game_over() is False
    assert board.current_player == PLAYER_WHITE
    assert not board.game_over


def test_check_game_over_leaves_playable_board_untouched():
    board = Board()
    assert board.check_game_over() is False
    assert board.current_player == PLAYER_BLACK
    assert not board.game_over


def test_is_terminal_is_pure():
    board = Board()
    board.is_terminal()
    assert not board.game_over
    assert board.current_player == PLAYER_BLACK


# ---------------------------------------------------------------------------
# Conversion and copying
# ---------------------------------------------------------------------------


def test_to_position_round_trip():
    board = Board()
    board.make_move(2, 3, PLAYER_BLACK)
    position = board.to_position()
    assert position.to_grid() == board.grid
    assert position.turn == board.current_player
    assert position.zobrist == position._compute_zobrist()


def test_load_position_replaces_contents():
    board = Board()
    position = Position().apply(3, 2)
    board.load_position(position)
    assert board.grid == position.to_grid()
    assert board.current_player == position.turn
    assert not board.game_over


def test_copy_is_deep():
    board = Board()
    clone = board.copy()
    clone.make_move(2, 3, PLAYER_BLACK)
    assert board.get_score() == (2, 2)
    assert clone.get_score() == (4, 1)


def test_legal_move_count_matches_list_length():
    board = Board()
    board.make_move(2, 3, PLAYER_BLACK)
    for player in (PLAYER_BLACK, PLAYER_WHITE):
        assert board.legal_move_count(player) == len(board.get_valid_moves(player))


def test_is_full_detects_filled_board():
    board = Board()
    assert not board.is_full()
    board.grid = [[PLAYER_BLACK] * 8 for _ in range(8)]
    assert board.is_full()


def test_make_move_switches_to_the_opponent_of_the_mover():
    """Replay paths must not depend on the board's own idea of the turn."""

    board = Board()
    board.current_player = PLAYER_WHITE
    assert board.make_move(2, 3, PLAYER_BLACK)
    assert board.current_player == PLAYER_WHITE
