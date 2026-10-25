"""Tests for the bitboard position and its equivalence with the board rules."""

from __future__ import annotations

import random

import pytest

from iago.core import Board, Position
from iago.core.bitboard import geometry_for, iter_bits, mask_to_cells
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE, opponent

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def test_initial_position_shape():
    position = Position()
    assert position.size == 8
    assert position.score() == (2, 2)
    assert position.turn == PLAYER_BLACK
    assert position.empty_count() == 60
    assert position.move_number() == 1


def test_initial_legal_moves_are_the_four_standard_openings():
    cells = set(Position().legal_move_list())
    assert cells == {(2, 3), (3, 2), (4, 5), (5, 4)}


def test_move_mask_matches_move_list():
    position = Position()
    assert set(mask_to_cells(position.legal_moves(), 8)) == set(
        position.legal_move_list()
    )


@pytest.mark.parametrize("size", [6, 8, 10])
def test_all_supported_sizes_start_with_four_moves(size):
    position = Position(size)
    assert position.score() == (2, 2)
    assert len(position.legal_move_list()) == 4


def test_iter_bits_yields_ascending_indices():
    assert list(iter_bits(0b1010_0100)) == [2, 5, 7]
    assert list(iter_bits(0)) == []


def test_geometry_is_cached():
    assert geometry_for(8) is geometry_for(8)


def test_geometry_rejects_unsupported_sizes():
    with pytest.raises(ValueError):
        geometry_for(3)


# ---------------------------------------------------------------------------
# Applying moves
# ---------------------------------------------------------------------------


def test_apply_matches_reference_board():
    board = Board()
    position = Position()
    board.make_move(2, 3, PLAYER_BLACK)
    position = position.apply(2, 3)
    assert position.to_grid() == board.grid
    assert position.turn == board.current_player


def test_apply_flips_the_expected_discs():
    position = Position().apply(2, 3)  # d3 flips d4
    assert position.disc_at(3, 3) == PLAYER_BLACK
    assert position.disc_at(2, 3) == PLAYER_BLACK
    assert position.score() == (4, 1)


def test_apply_rejects_illegal_move():
    with pytest.raises(ValueError):
        Position().apply(0, 0)


def test_flips_for_returns_mask_of_cells():
    position = Position()
    mask = position.flips_for(2, 3)
    assert mask_to_cells(mask, 8) == [(3, 3)]
    assert position.flips_for(0, 0) == 0


def test_pass_turn_preserves_board_and_swaps_turn():
    position = Position()
    passed = position.pass_turn()
    assert passed.black == position.black
    assert passed.white == position.white
    assert passed.turn == PLAYER_WHITE
    assert passed.zobrist != position.zobrist


def test_with_turn_is_identity_when_unchanged():
    position = Position()
    assert position.with_turn(PLAYER_BLACK) is position
    assert position.with_turn(PLAYER_WHITE).turn == PLAYER_WHITE


# ---------------------------------------------------------------------------
# Zobrist hashing
# ---------------------------------------------------------------------------


def test_zobrist_is_deterministic():
    assert Position().zobrist == Position().zobrist


def test_zobrist_matches_full_recomputation_after_many_moves():
    position = Position()
    rng = random.Random(7)
    for _ in range(30):
        moves = position.legal_move_list()
        if not moves:
            position = position.pass_turn()
            continue
        position = position.apply(*rng.choice(moves))
        assert position.zobrist == position._compute_zobrist()


def test_different_positions_have_different_hashes():
    first = Position().apply(2, 3)
    second = Position().apply(3, 2)
    assert first.zobrist != second.zobrist


def test_equal_positions_hash_equally():
    position = Position().apply(2, 3).apply(2, 4)
    position = position.apply(*position.legal_move_list()[0])
    rebuilt = Position.from_grid(position.to_grid()).with_turn(position.turn)
    assert rebuilt == position
    assert rebuilt.zobrist == position.zobrist


def test_transpositions_reached_by_different_move_orders_hash_equally():
    seen: dict[tuple, set[int]] = {}
    frontier = [Position()]
    for _ in range(3):
        next_frontier = []
        for position in frontier:
            for move in position.legal_move_list():
                child = position.apply(*move)
                key = (child.size, child.black, child.white, child.turn)
                seen.setdefault(key, set()).add(child.zobrist)
                next_frontier.append(child)
        frontier = next_frontier
    assert seen, "expected at least one reachable position"
    assert all(len(hashes) == 1 for hashes in seen.values())


# ---------------------------------------------------------------------------
# Terminal detection
# ---------------------------------------------------------------------------


def test_full_board_is_terminal():
    grid = [[PLAYER_BLACK] * 8 for _ in range(8)]
    position = Position.from_grid(grid)
    assert position.is_terminal()
    assert position.result() == PLAYER_BLACK


def test_draw_result():
    grid = [
        [PLAYER_BLACK if (r + c) % 2 == 0 else PLAYER_WHITE for c in range(8)]
        for r in range(8)
    ]
    position = Position.from_grid(grid)
    assert position.result() == 0


def test_position_result_is_none_while_playable():
    assert Position().result() is None
    assert not Position().is_terminal()


# ---------------------------------------------------------------------------
# Equivalence with the reference rules (fuzz)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [6, 8, 10])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_position_and_board_agree_over_random_games(size, seed):
    rng = random.Random(seed * 100 + size)
    board = Board(size)
    position = Position(size)

    for _ in range(120):
        for player in (PLAYER_BLACK, PLAYER_WHITE):
            expected = set(board.get_valid_moves(player))
            actual = set(
                mask_to_cells(
                    position.geometry.move_mask(
                        position.black if player == PLAYER_BLACK else position.white,
                        position.white if player == PLAYER_BLACK else position.black,
                    ),
                    size,
                )
            )
            assert expected == actual, f"move mismatch for player {player}"

        moves = board.get_valid_moves(board.current_player)
        if not moves:
            if board.is_terminal():
                break
            board.check_game_over()
            position = position.pass_turn()
            assert board.current_player == position.turn
            continue

        row, col = rng.choice(moves)
        expected_flips = set(board.get_flips(row, col, board.current_player))
        actual_flips = set(mask_to_cells(position.flips_for(row, col), size))
        assert expected_flips == actual_flips

        board.make_move(row, col, board.current_player)
        position = position.apply(row, col)
        assert position.to_grid() == board.grid
        assert position.turn == board.current_player


def _perft(position: Position, depth: int) -> int:
    if depth == 0:
        return 1
    moves = position.legal_move_list()
    if not moves:
        if position.is_terminal():
            return 1
        return _perft(position.pass_turn(), depth)
    return sum(_perft(position.apply(*move), depth - 1) for move in moves)


@pytest.mark.parametrize(
    "depth,expected",
    [(1, 4), (2, 12), (3, 56), (4, 244), (5, 1396), (6, 8200)],
)
def test_perft_counts_match_published_values(depth, expected):
    assert _perft(Position(), depth) == expected


def test_opponent_helper():
    assert opponent(PLAYER_BLACK) == PLAYER_WHITE
    assert opponent(PLAYER_WHITE) == PLAYER_BLACK
