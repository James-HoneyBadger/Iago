"""End-to-end controller tests (headless)."""

from __future__ import annotations

import time

import pygame as pg
import pytest

from iago.app import paths, persistence
from iago.app.game import Game, LaunchOptions
from iago.core.constants import (
    MODE_AVA,
    MODE_HVAI,
    MODE_HVH,
    PLAYER_BLACK,
    PLAYER_WHITE,
)


@pytest.fixture()
def game(data_dir):
    instance = Game(LaunchOptions(mode=MODE_HVAI, level=1, theme="classic"))
    if instance.overlay == "resume":
        instance._discard_resume()
    yield instance
    instance.worker.cancel()
    instance.hint_worker.cancel()
    instance.review_worker.cancel()
    pg.display.set_mode((320, 240))


def pump(game: Game, frames: int = 30, delay: float = 0.002) -> None:
    for _ in range(frames):
        game.handle_events()
        game.update(1.0 / 60.0)
        game.draw()
        time.sleep(delay)


def first_legal(game: Game):
    moves = game.session.legal_moves()
    assert moves, "expected a legal move"
    return moves[0]


# ---------------------------------------------------------------------------


def test_new_game_state(game):
    assert game.session.ply == 0
    assert game.session.mode == MODE_HVAI
    assert game.renderer.layout.board_size == 8
    game.draw()
    assert len(game.renderer.menubar_buttons) >= 5


def test_human_move_triggers_ai_reply(game):
    move = first_legal(game)
    game.on_board_click(*move)
    assert game.session.ply == 1
    assert game.session.current_player == PLAYER_WHITE

    deadline = time.perf_counter() + 5.0
    while time.perf_counter() < deadline and game.session.ply < 2:
        pump(game, frames=3)
    assert game.session.ply >= 2, "the engine never answered"
    assert game.session.current_player == PLAYER_BLACK


def test_illegal_click_does_not_change_the_board(game):
    game.on_board_click(0, 0)
    assert game.session.ply == 0


def test_click_while_ai_thinks_is_ignored(game):
    game.on_board_click(*first_legal(game))
    game.update(1.0 / 60.0)
    plies = game.session.ply
    game.on_board_click(0, 0)
    assert game.session.ply == plies


def test_undo_pairs_back_to_human_turn(game):
    game.on_board_click(*first_legal(game))
    deadline = time.perf_counter() + 5.0
    while time.perf_counter() < deadline and game.session.ply < 2:
        pump(game, frames=3)
    assert game.session.ply >= 2

    game._undo()
    assert game.session.ply == 0
    assert game.session.current_player == PLAYER_BLACK


def test_redo_after_undo(game):
    game.on_board_click(*first_legal(game))
    game._undo()
    assert game.session.ply == 0
    game._redo()
    assert game.session.ply == 1


def test_new_game_clears_history(game):
    game.on_board_click(*first_legal(game))
    game._new_game()
    assert game.session.ply == 0
    assert game.overlay is None


def test_theme_cycle_updates_settings_and_renderer(game):
    original = game.settings.theme
    game._cycle_theme()
    assert game.settings.theme != original
    assert game.renderer.theme.key == game.settings.theme


def test_level_cycle_and_direct_set(game):
    game._set_level(5)
    assert game.settings.ai_level == 5
    assert game.engine.difficulty == 5
    assert game.session.level == 5
    game._cycle_level()
    assert game.settings.ai_level == 1


def test_board_size_change_starts_a_new_game(game):
    game._set_board_size(10)
    assert game.settings.board_size == 10
    assert game.session.size == 10
    assert game.renderer.layout.board_size == 10
    assert game.session.ply == 0


def test_options_overlay_opens_and_closes(game):
    game._open_options()
    assert game.overlay == "options"
    game.draw()
    target = next(t for t in game.renderer.targets if t.action == "options_tab")
    game.on_click(target.rect.center)
    assert game.overlay == "options"
    game._close_overlay()
    assert game.overlay is None


def test_help_and_stats_overlays(game):
    game._open_help()
    assert game.overlay == "help"
    game._close_overlay()
    game._open_stats()
    assert game.overlay == "stats"
    game._close_overlay()


def test_mute_toggle(game):
    original = game.settings.sound_enabled
    game._toggle_sound()
    assert game.settings.sound_enabled is not original
    assert game.sound.enabled is (not original)


def test_save_and_load_round_trip(game):
    game.on_board_click(*first_legal(game))
    game._save_game()
    assert paths.save_path().exists()

    saved_plies = game.session.ply
    game._new_game()
    assert game.session.ply == 0

    game._load_game()
    assert game.session.ply == saved_plies


def test_autosave_is_written_on_quit_path(game):
    game.on_board_click(*first_legal(game))
    game._autosave()
    assert paths.autosave_path().exists()
    saved = persistence.load_game(paths.autosave_path())
    assert saved.move_count == 1


def test_resume_prompt_appears_for_an_autosave(data_dir):
    payload = persistence.build_save_payload(
        board_size=8,
        mode=MODE_HVAI,
        level=2,
        player_color=PLAYER_BLACK,
        moves=[(PLAYER_BLACK, 2, 3)],
        game_over=False,
        winner=None,
    )
    persistence.save_game_file(payload, paths.autosave_path())
    instance = Game(LaunchOptions(mode=MODE_HVAI, level=2))
    try:
        assert instance.overlay == "resume"
        instance._resume_game()
        assert instance.session.ply == 1
        assert instance.overlay is None
    finally:
        instance.worker.cancel()
        pg.display.set_mode((320, 240))


def test_discard_resume_removes_the_autosave(data_dir):
    payload = persistence.build_save_payload(
        board_size=8,
        mode=MODE_HVAI,
        level=2,
        player_color=PLAYER_BLACK,
        moves=[(PLAYER_BLACK, 2, 3)],
        game_over=False,
        winner=None,
    )
    persistence.save_game_file(payload, paths.autosave_path())
    instance = Game(LaunchOptions())
    try:
        instance._discard_resume()
        assert not paths.autosave_path().exists()
    finally:
        instance.worker.cancel()
        pg.display.set_mode((320, 240))


def test_game_over_records_stats_and_shows_overlay(game):
    game.session.reset(mode=MODE_HVAI, player_color=PLAYER_BLACK, level=1)
    guard = 0
    while not game.session.game_over and guard < 200:
        guard += 1
        moves = game.session.legal_moves()
        if not moves:
            game.session.play_pending_pass()
            continue
        game.session.apply_move(*moves[0])
    game._end_game()
    assert game.session.game_over
    assert game.overlay == "gameover"
    assert game.stats.games_played == 1
    assert game.stats.games_played == (
        game.stats.games_won + game.stats.games_lost + game.stats.games_drawn
    )
    game.draw()


def test_clock_flag_ends_the_game(game):
    game.session.clock.mode = "blitz"
    game.session.clock.base = 0.01
    game.session.clock.start(PLAYER_BLACK, time.monotonic() - 5.0)
    game._tick_clock()
    assert game.session.game_over
    assert game.session.winner == PLAYER_WHITE
    assert game.game_over_reason == "time"


def test_review_selection_shows_a_past_position(game):
    game.on_board_click(*first_legal(game))
    game._set_review_ply(0)
    assert game.selected_ply == 0
    model = game._build_model()
    assert model.display_board is not None
    assert model.display_board.grid[3][3] == PLAYER_WHITE
    game._set_review_ply(1)
    assert game.selected_ply == 1
    game._set_review_ply(9)
    assert game.selected_ply == 1  # clamped to the number of moves


def test_hint_request_populates_pending_hint(game):
    game._request_hint()
    deadline = time.perf_counter() + 5.0
    while time.perf_counter() < deadline and game.pending_hint is None:
        pump(game, frames=2, delay=0.005)
    assert game.pending_hint in game.session.legal_moves()


def test_ai_vs_ai_advances_without_input(data_dir):
    instance = Game(LaunchOptions(mode=MODE_AVA, level=1))
    instance.ava_speed = 0
    try:
        deadline = time.perf_counter() + 10.0
        while time.perf_counter() < deadline and instance.session.ply < 2:
            pump(instance, frames=2, delay=0.005)
        assert instance.session.ply >= 2
    finally:
        instance.worker.cancel()
        pg.display.set_mode((320, 240))


def test_two_player_mode_accepts_both_colours(data_dir):
    instance = Game(LaunchOptions(mode=MODE_HVH, level=1))
    try:
        assert instance.session.is_human_turn()
        instance.on_board_click(*first_legal(instance))
        assert instance.session.current_player == PLAYER_WHITE
        assert instance.session.is_human_turn()
        instance.on_board_click(*first_legal(instance))
        assert instance.session.ply == 2
    finally:
        instance.worker.cancel()
        pg.display.set_mode((320, 240))


def test_settings_persist_across_instances(data_dir):
    instance = Game(LaunchOptions(theme="ocean", level=4))
    instance.settings.show_coordinates = False
    instance._save_settings()
    instance.worker.cancel()
    pg.display.set_mode((320, 240))

    second = Game()
    try:
        assert second.settings.theme == "ocean"
        assert second.settings.ai_level == 4
        assert second.settings.show_coordinates is False
    finally:
        second.worker.cancel()
        pg.display.set_mode((320, 240))
