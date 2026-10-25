"""Tests for settings, statistics and achievements."""

from __future__ import annotations

import pytest

from iago.ai.levels import MAX_DIFFICULTY
from iago.app.achievements import (
    ACHIEVEMENTS,
    GameSummary,
    evaluate as evaluate_achievements,
    progress,
)
from iago.ui.layout import compute_layout
from iago.app.settings import GameSettings, GameStats
from iago.core.constants import PLAYER_BLACK, PLAYER_WHITE
from iago.ui.theme import DEFAULT_THEME_KEY

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_defaults_are_valid():
    settings = GameSettings().validated()
    assert settings.theme == DEFAULT_THEME_KEY
    assert settings.board_size == 8
    assert settings.ai_level == 3
    assert settings.player_color == PLAYER_BLACK
    assert settings.sound_enabled
    assert 0.0 <= settings.sound_volume <= 1.0


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("theme", "nope", DEFAULT_THEME_KEY),
        ("mode", "nope", "hvai"),
        ("board_size", 7, 8),
        ("player_color", 9, PLAYER_BLACK),
        ("ai_level", 99, MAX_DIFFICULTY),
        ("ai_level", -4, 1),
        ("clock_mode", "nope", "off"),
        ("sound_volume", 4.2, 1.0),
        ("ui_scale", 0.1, 0.75),
        ("window_width", 10, 760),
    ],
)
def test_validation_clamps_and_falls_back(field, value, expected):
    settings = GameSettings(**{field: value}).validated()
    assert getattr(settings, field) == expected


def test_round_trip_dict():
    settings = GameSettings(theme="ocean", board_size=10, ai_level=5, sound_volume=0.25)
    restored = GameSettings.from_dict(settings.to_dict())
    assert restored == settings.validated()


def test_from_dict_ignores_unknown_keys():
    settings = GameSettings.from_dict({"theme": "wood", "bogus": 1})
    assert settings.theme == "wood"


def test_legacy_settings_migrate_difficulty_names():
    legacy = {
        "theme": "Classic",
        "sound_enabled": False,
        "show_hints": False,
        "ai_difficulty": "EXPERT",
        "board_size": 8,
        "player_color": 2,
        "animations": False,
    }
    settings = GameSettings.from_legacy(legacy)
    assert settings.ai_level == 4
    assert settings.sound_enabled is False
    assert settings.show_hints is False
    assert settings.player_color == PLAYER_WHITE


def test_legacy_settings_numeric_difficulty():
    assert GameSettings.from_legacy({"ai_difficulty": 5}).ai_level == 5


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_record_result_win():
    stats = GameStats()
    won = stats.record_result(
        level=2,
        winner=PLAYER_BLACK,
        player_color=PLAYER_BLACK,
        moves=40,
        player_score=40,
        opponent_score=24,
    )
    assert won
    assert stats.games_played == 1
    assert stats.games_won == 1
    assert stats.current_streak == 1
    assert stats.win_streak == 1
    assert stats.best_score == 40
    assert stats.fastest_win_moves == 40
    assert stats.level_record(2).won == 1


def test_record_result_loss_and_draw():
    stats = GameStats()
    stats.record_result(
        level=3,
        winner=PLAYER_WHITE,
        player_color=PLAYER_BLACK,
        moves=50,
        player_score=20,
        opponent_score=44,
    )
    assert stats.games_lost == 1
    assert stats.current_streak == -1
    assert stats.loss_streak == 1

    stats.record_result(
        level=3,
        winner=0,
        player_color=PLAYER_BLACK,
        moves=50,
        player_score=32,
        opponent_score=32,
    )
    assert stats.games_drawn == 1
    assert stats.current_streak == 0


def test_streaks_track_best_and_current():
    stats = GameStats()
    for _ in range(3):
        stats.record_result(
            level=1,
            winner=PLAYER_BLACK,
            player_color=PLAYER_BLACK,
            moves=30,
            player_score=64,
            opponent_score=0,
        )
    stats.record_result(
        level=1,
        winner=PLAYER_WHITE,
        player_color=PLAYER_BLACK,
        moves=30,
        player_score=0,
        opponent_score=64,
    )
    assert stats.win_streak == 3
    assert stats.current_streak == -1


def test_average_moves_and_win_rate():
    stats = GameStats()
    stats.record_result(
        level=1,
        winner=PLAYER_BLACK,
        player_color=PLAYER_BLACK,
        moves=40,
        player_score=40,
        opponent_score=20,
    )
    stats.record_result(
        level=1,
        winner=PLAYER_WHITE,
        player_color=PLAYER_BLACK,
        moves=60,
        player_score=20,
        opponent_score=40,
    )
    assert stats.average_moves == 50
    assert stats.win_rate == 0.5


def test_stats_round_trip():
    stats = GameStats(games_played=5, games_won=3, achievements=["first_win"])
    stats.level_record(4).won = 2
    restored = GameStats.from_dict(stats.to_dict())
    assert restored.games_played == 5
    assert restored.by_level[4].won == 2
    assert restored.achievements == ["first_win"]


def test_empty_stats_properties():
    stats = GameStats()
    assert stats.win_rate == 0.0
    assert stats.average_moves == 0.0


def test_unlock_is_idempotent():
    stats = GameStats()
    assert stats.unlock("first_win")
    assert not stats.unlock("first_win")
    assert stats.has_achievement("first_win")


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


def summary(**overrides) -> GameSummary:
    base = dict(
        mode="hvai",
        level=1,
        player_color=PLAYER_BLACK,
        winner=PLAYER_BLACK,
        moves=60,
        board_size=8,
        black_score=40,
        white_score=24,
        duration=120.0,
        lowest_probability=0.5,
    )
    base.update(overrides)
    return GameSummary(**base)


def test_achievement_catalogue_is_unique():
    keys = [achievement.key for achievement in ACHIEVEMENTS]
    assert len(keys) == len(set(keys))
    assert all(
        achievement.title and achievement.description for achievement in ACHIEVEMENTS
    )


def test_first_win_unlocks():
    stats = GameStats()
    stats.record_result(
        level=1,
        winner=PLAYER_BLACK,
        player_color=PLAYER_BLACK,
        moves=60,
        player_score=40,
        opponent_score=24,
    )
    unlocked = evaluate_achievements(stats, summary())
    keys = {achievement.key for achievement in unlocked}
    assert "first_win" in keys
    assert stats.has_achievement("first_win")


def test_shutout_and_flawless_and_comeback():
    stats = GameStats()
    stats.record_result(
        level=1,
        winner=PLAYER_BLACK,
        player_color=PLAYER_BLACK,
        moves=20,
        player_score=64,
        opponent_score=0,
    )
    unlocked = evaluate_achievements(
        stats,
        summary(moves=20, black_score=64, white_score=0, lowest_probability=0.1),
    )
    keys = {achievement.key for achievement in unlocked}
    assert {"shutout", "perfect_game", "comeback", "quick_win"} <= keys


def test_beat_master_requires_won_game():
    stats = GameStats()
    stats.record_result(
        level=5,
        winner=PLAYER_BLACK,
        player_color=PLAYER_BLACK,
        moves=60,
        player_score=40,
        opponent_score=24,
    )
    unlocked = evaluate_achievements(stats, summary(level=5))
    assert any(achievement.key == "beat_master" for achievement in unlocked)

    other = GameStats()
    other.record_result(
        level=5,
        winner=PLAYER_WHITE,
        player_color=PLAYER_BLACK,
        moves=60,
        player_score=20,
        opponent_score=44,
    )
    unlocked = evaluate_achievements(other, summary(level=5, winner=PLAYER_WHITE))
    assert all(achievement.key != "beat_master" for achievement in unlocked)


def test_grand_slam_needs_every_level():
    stats = GameStats()
    for level in range(1, MAX_DIFFICULTY + 1):
        stats.level_record(level).won = 1
    unlocked = evaluate_achievements(stats, summary())
    assert any(achievement.key == "grand_slam" for achievement in unlocked)


def test_progress_reports_locked_state():
    stats = GameStats()
    rows = progress(stats)
    assert len(rows) == len(ACHIEVEMENTS)
    assert all(not done for _, done in rows)


def test_summary_player_score_switches_with_colour():
    white = summary(
        player_color=PLAYER_WHITE, winner=PLAYER_WHITE, black_score=20, white_score=44
    )
    assert white.player_score == 44
    assert white.opponent_score == 20
    assert white.won


def test_ui_scale_is_clamped_to_the_shared_range():
    from iago.ui.layout import MAX_UI_SCALE, MIN_UI_SCALE

    assert GameSettings(ui_scale=9.0).validated().ui_scale == MAX_UI_SCALE
    assert GameSettings(ui_scale=0.1).validated().ui_scale == MIN_UI_SCALE
    layout_test_scale = MAX_UI_SCALE
    assert compute_layout((1200, 900), 8, layout_test_scale).ui_scale == MAX_UI_SCALE
    assert compute_layout((1200, 900), 8, 4.0).ui_scale == MAX_UI_SCALE
