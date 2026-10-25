"""Tests for algebraic notation and opening identification."""

from __future__ import annotations

import pytest

from iago.core import Board
from iago.core.notation import (
    OPENINGS,
    identify_opening,
    move_name,
    move_names,
    opening_label,
    parse_move,
    sequence_to_string,
)
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE


def test_move_names_use_column_letters_and_one_based_rows():
    assert move_name(0, 0) == "a1"
    assert move_name(2, 3) == "d3"
    assert move_name(7, 7) == "h8"
    assert move_name(9, 9) == "j10"


def test_move_name_rejects_negative_coordinates():
    with pytest.raises(ValueError):
        move_name(-1, 0)


def test_parse_move_round_trips():
    for row in range(8):
        for col in range(8):
            assert parse_move(move_name(row, col)) == (row, col)


def test_parse_move_is_case_insensitive_and_trims():
    assert parse_move("  D3 ") == (2, 3)


@pytest.mark.parametrize("text", ["", "d", "3", "z3", "d0", "dd", "d-1"])
def test_parse_move_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_move(text)


def test_move_names_and_sequence_formatting():
    moves = [(PLAYER_BLACK, 2, 3), (PLAYER_WHITE, 2, 4), (PLAYER_BLACK, 2, 2)]
    assert move_names(moves) == ["d3", "e3", "c3"]
    assert sequence_to_string(moves) == "d3 e3 c3"


def test_identify_opening_matches_known_line():
    opening = identify_opening([(PLAYER_BLACK, 2, 3), (PLAYER_WHITE, 2, 4)])
    assert opening is not None
    assert opening.name == "Tiger"
    assert opening_label([(PLAYER_BLACK, 2, 3), (PLAYER_WHITE, 2, 4)]) == "Tiger"


def test_identify_opening_returns_none_for_unknown_line():
    assert identify_opening([(PLAYER_BLACK, 0, 0)]) is None
    assert identify_opening([]) is None


def test_identify_opening_is_size_limited():
    moves = [(PLAYER_BLACK, 2, 3), (PLAYER_WHITE, 2, 4)]
    assert identify_opening(moves, size=10) is None


def test_longest_prefix_wins():
    # A line that is a prefix of another should resolve to the longer opening.
    assert len(OPENINGS) >= 6
    opening = identify_opening([(PLAYER_BLACK, 2, 3), (PLAYER_WHITE, 2, 4)])
    assert opening is not None and opening.moves == ("d3", "e3")


def test_all_openings_have_unique_names_and_lines():
    names = [opening.name for opening in OPENINGS]
    lines = [opening.moves for opening in OPENINGS]
    assert len(names) == len(set(names))
    assert len(lines) == len(set(lines))


def test_all_opening_moves_are_legal_from_the_start():
    for opening in OPENINGS:
        board = Board()
        for index, name in enumerate(opening.moves):
            row, col = parse_move(name)
            player = PLAYER_BLACK if index % 2 == 0 else PLAYER_WHITE
            assert board.current_player == player
            assert board.is_valid_move(
                row, col, player
            ), f"{opening.name}: {name} is not legal for player {player}"
            board.make_move(row, col, player)
        expected = PLAYER_BLACK if len(opening.moves) % 2 == 0 else PLAYER_WHITE
        assert board.current_player == expected
