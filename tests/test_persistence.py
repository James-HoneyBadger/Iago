"""Tests for persistence: settings, statistics and saved games."""

from __future__ import annotations

import json

import pytest

from iago.app import paths, persistence
from iago.app.persistence import SavedGame
from iago.app.settings import GameSettings, GameStats
from iago.core.board import Board
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE
from iago.util.errors import SaveFileError


def _legal_moves(count: int = 4):  # noqa: D401 - helper
    board = Board()
    moves = []
    while len(moves) < count:
        options = board.get_valid_moves(board.current_player)
        if not options:
            board.check_game_over()
            continue
        row, col = options[0]
        moves.append((board.current_player, row, col))
        board.make_move(row, col, board.current_player)
    return moves


MOVES = _legal_moves()


# ---------------------------------------------------------------------------
# Paths and atomic writes
# ---------------------------------------------------------------------------


def test_data_dir_honours_override(data_dir):
    assert paths.data_dir() == data_dir
    assert paths.settings_path().parent == data_dir
    assert paths.autosave_path().name == "autosave.json"


def test_save_path_sanitises_names(data_dir):
    assert paths.save_path("my game/../x").name == "mygamex.json"


def test_atomic_write_creates_valid_json(tmp_path):
    target = tmp_path / "nested" / "file.json"
    persistence.atomic_write_json(target, {"a": 1})
    assert json.loads(target.read_text())["a"] == 1
    assert not list(target.parent.glob("*.tmp"))


def test_read_json_rejects_missing_and_invalid(tmp_path):
    with pytest.raises(SaveFileError):
        persistence.read_json(tmp_path / "missing.json")

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(SaveFileError):
        persistence.read_json(broken)

    wrong = tmp_path / "list.json"
    wrong.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(SaveFileError):
        persistence.read_json(wrong)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_round_trip(data_dir):
    settings = GameSettings(theme="ocean", ai_level=4, sound_volume=0.3)
    persistence.save_settings(settings)
    loaded = persistence.load_settings()
    assert loaded.theme == "ocean"
    assert loaded.ai_level == 4
    assert loaded.sound_volume == pytest.approx(0.3)


def test_settings_default_when_absent(data_dir):
    loaded = persistence.load_settings()
    assert loaded.theme == GameSettings().theme


def test_settings_corrupt_file_falls_back(data_dir):
    paths.settings_path().write_text("{oops", encoding="utf-8")
    loaded = persistence.load_settings()
    assert loaded.board_size == 8


def test_settings_legacy_migration(data_dir, tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    legacy = legacy_dir / "settings.json"
    legacy.write_text(
        json.dumps({"settings": {"ai_difficulty": "HARD", "board_size": 10}}),
        encoding="utf-8",
    )
    loaded = persistence.load_settings(path=legacy)
    assert loaded.ai_level == 3
    assert loaded.board_size == 10


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_stats_round_trip(data_dir):
    stats = GameStats(games_played=3, games_won=2)
    stats.level_record(2).won = 2
    persistence.save_stats(stats)
    loaded = persistence.load_stats()
    assert loaded.games_played == 3
    assert loaded.by_level[2].won == 2


def test_stats_legacy_migration(tmp_path):
    legacy = tmp_path / "stats.json"
    legacy.write_text(
        json.dumps(
            {
                "games_played": 7,
                "games_won": 4,
                "games_lost": 2,
                "games_drawn": 1,
                "total_moves": 350,
                "best_score": 44,
                "win_streak": 3,
                "loss_streak": 1,
                "current_streak": 2,
            }
        ),
        encoding="utf-8",
    )
    loaded = persistence.load_stats(path=legacy)
    assert loaded.games_played == 7
    assert loaded.games_won == 4
    assert loaded.current_streak == 2


def test_stats_corrupt_file_returns_defaults(data_dir):
    paths.stats_path().write_text("nonsense", encoding="utf-8")
    assert persistence.load_stats().games_played == 0


# ---------------------------------------------------------------------------
# Saved games
# ---------------------------------------------------------------------------


def payload(**overrides):
    base = persistence.build_save_payload(
        board_size=8,
        mode="hvai",
        level=4,
        player_color=PLAYER_BLACK,
        moves=MOVES,
        game_over=False,
        winner=None,
        clocks={"mode": "blitz", "elapsed": {"1": 12.0, "2": 9.5}},
    )
    base.update(overrides)
    return base


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "game.json"
    persistence.save_game_file(payload(), path)
    saved = persistence.load_game(path)
    assert saved.board_size == 8
    assert saved.mode == "hvai"
    assert saved.level == 4
    assert saved.moves == MOVES
    assert saved.clocks["mode"] == "blitz"


def test_replay_rebuilds_the_board():
    saved = SavedGame(moves=MOVES)
    board = saved.replay()
    reference = Board()
    for player, row, col in MOVES:
        reference.make_move(row, col, player)
    assert board.grid == reference.grid


def test_notation_list():
    from iago.core.notation import move_name

    expected = [move_name(row, col) for _, row, col in MOVES]
    assert SavedGame(moves=MOVES).notation() == expected


def test_illegal_move_in_save_is_rejected(tmp_path):
    bad = payload(moves=[(PLAYER_BLACK, 0, 0)])
    path = tmp_path / "bad.json"
    persistence.save_game_file(bad, path)
    with pytest.raises(SaveFileError):
        persistence.load_game(path)


def test_legacy_v3_save_loads(tmp_path):
    legacy = {
        "board_grid": Board().grid,
        "current_player": PLAYER_BLACK,
        "black_score": 2,
        "white_score": 2,
        "game_over": False,
        "winner": None,
        "move_log": [[1, 2, 3], [2, 2, 4]],
        "settings": {
            "show_hints": True,
            "ai_difficulty": 3,
            "board_size": 8,
            "player_color": 1,
            "game_mode": "hvai",
        },
        "timestamp": 1700000000.0,
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    saved = persistence.load_game(path)
    assert saved.move_count == 2
    assert saved.level == 3
    assert saved.mode == "hvai"


def test_unknown_mode_falls_back(tmp_path):
    path = tmp_path / "odd.json"
    persistence.save_game_file(payload(mode="nonsense"), path)
    assert persistence.load_game(path).mode == "hvai"


def test_invalid_board_size_rejected(tmp_path):
    path = tmp_path / "small.json"
    persistence.save_game_file(payload(board_size=2), path)
    with pytest.raises(SaveFileError):
        persistence.load_game(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(SaveFileError):
        persistence.load_game(tmp_path / "nope.json")


def test_autosave_lifecycle(data_dir):
    assert persistence.find_autosave() is None
    persistence.save_game_file(payload(), paths.autosave_path())
    found = persistence.find_autosave()
    assert found is not None and found.exists()
    persistence.delete_autosave()
    assert persistence.find_autosave() is None


def test_clock_elapsed_parses_and_filters_entries():
    saved = SavedGame(
        moves=MOVES,
        clocks={
            "mode": "blitz",
            "elapsed": {"1": 12.0, "2": "9.5", "3": 4.0, "x": 1.0, "1.5": 2.0},
        },
    )
    assert saved.clock_elapsed() == {PLAYER_BLACK: 12.0, PLAYER_WHITE: 9.5}


def test_clock_elapsed_rejects_bad_payloads():
    assert SavedGame(moves=MOVES, clocks={}).clock_elapsed() == {}
    assert SavedGame(moves=MOVES, clocks={"elapsed": [1, 2]}).clock_elapsed() == {}
    assert SavedGame(moves=MOVES, clocks={"elapsed": {"1": -5.0}}).clock_elapsed() == {}
