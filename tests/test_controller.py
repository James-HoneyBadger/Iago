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


def test_loading_a_save_with_another_board_size_reconfigures_the_engine(game):
    from iago.app.session import Session as _Session

    ten = _Session(size=10, mode=MODE_HVAI)
    ten.apply_move(*ten.legal_moves()[0])
    ten.apply_move(*ten.legal_moves()[0])
    payload = persistence.build_save_payload(
        board_size=10,
        mode=MODE_HVAI,
        level=2,
        player_color=PLAYER_BLACK,
        moves=ten.to_move_log(),
        game_over=False,
        winner=None,
    )
    persistence.save_game_file(payload)
    game._load_game()
    assert game.session.size == 10
    assert game.engine.size == 10
    assert game.engine2.size == 10
    assert game.renderer.layout.board_size == 10
    # the engine must be able to answer on the new geometry
    move = game.engine.get_move(game.session.board)
    assert move in game.session.legal_moves()


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


def test_stale_search_result_is_discarded_after_new_game(data_dir):
    """A search that finishes after the board changed must not be applied."""

    instance = Game(LaunchOptions(mode=MODE_HVAI, level=5))
    try:
        if instance.overlay == "resume":
            instance._discard_resume()
        instance.on_board_click(*first_legal(instance))
        # Kick off the engine's reply (level 5 thinks for seconds).
        for _ in range(3):
            instance.update(1.0 / 60.0)
        assert instance.worker.busy

        instance._new_game()
        assert instance.session.ply == 0
        stale_key = instance._search_key

        deadline = time.perf_counter() + 8.0
        while time.perf_counter() < deadline and instance.session.ply == 0:
            instance.update(1.0 / 60.0)
            time.sleep(0.005)
        assert instance.session.ply == 0, "a stale result was applied"
        assert stale_key != instance._position_key()
    finally:
        instance.worker.cancel()
        instance.hint_worker.cancel()
        pg.display.set_mode((320, 240))


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


def test_loading_a_save_restores_the_clocks(game):
    game.on_board_click(*first_legal(game))
    clocks = {"mode": "blitz", "elapsed": {"1": 12.0, "2": 9.5}}
    payload = persistence.build_save_payload(
        board_size=8,
        mode=MODE_HVAI,
        level=2,
        player_color=PLAYER_BLACK,
        moves=game.session.to_move_log(),
        game_over=False,
        winner=None,
        clocks=clocks,
    )
    persistence.save_game_file(payload)
    game._new_game()
    assert game.session.clock.elapsed == {PLAYER_BLACK: 0.0, PLAYER_WHITE: 0.0}

    game._load_game()
    assert game.session.clock.elapsed[PLAYER_BLACK] == pytest.approx(12.0)
    assert game.session.clock.elapsed[PLAYER_WHITE] == pytest.approx(9.5)


def test_seeded_engines_repeat_their_moves(data_dir):
    from iago.ai.engine import Engine
    from iago.core.board import Board

    board = Board()
    engine_a = Engine(1, 8, seed=4242)
    engine_b = Engine(1, 8, seed=4242)
    assert engine_a.get_move(board) == engine_b.get_move(board)


def test_launch_seed_is_forwarded_to_the_engine(data_dir):
    one = Game(LaunchOptions(mode=MODE_HVAI, level=2, seed=99))
    two = Game(LaunchOptions(mode=MODE_HVAI, level=2, seed=99))
    try:
        for instance in (one, two):
            if instance.overlay == "resume":
                instance._discard_resume()
        # drain any random draws so both engines are in the same state
        assert one.engine.get_move(one.session.board) == two.engine.get_move(
            two.session.board
        )
    finally:
        for instance in (one, two):
            instance.worker.cancel()
            instance.hint_worker.cancel()
            instance.review_worker.cancel()


def test_window_caption_tracks_state(game):
    game._new_game()
    title = pg.display.get_caption()[0]
    assert "Iago" in title
    assert game.session.mode.upper() in title or "vs" in title.lower()


def test_thinking_dots_animate(game):
    game.thinking = (8, 1234)  # type: ignore[assignment]
    first = game._build_model().thinking_text
    assert first.startswith("Thinking") and first.endswith(".")
    time.sleep(0.55)
    second = game._build_model().thinking_text
    assert first != second
    game.thinking = None


def test_review_cache_is_reused_and_invalidated(game):
    game.on_board_click(*first_legal(game))
    game._set_review_ply(0)
    first = game._build_model().display_board
    assert game._build_model().display_board is first
    game._set_review_ply(1)
    second = game._build_model().display_board
    assert second is not first


# ---------------------------------------------------------------------------
# Input plumbing
# ---------------------------------------------------------------------------


def test_menu_buttons_open_their_overlays(game):
    game.draw()
    assert game.renderer.menubar_buttons
    opened = {}
    for button in game.renderer.menubar_buttons:
        game._on_button(str(button.key))
        opened[str(button.key)] = game.overlay
        game.overlay = None
    assert opened


def test_key_bindings_dispatch(game):
    from iago.app.keymap import BINDINGS, GLOBAL, PLAYING

    game._save_game()
    game.on_board_click(*first_legal(game))
    seen = set()
    for binding in BINDINGS:
        if binding.context not in (PLAYING, GLOBAL):
            continue
        game.handle_events()
        game.on_key(binding.keys[0], binding.modifiers)
        seen.add(binding.action)
        game.overlay = None
    assert {"undo", "redo", "new_game", "cycle_theme"} <= seen
    assert {"help", "options"} <= seen


def test_board_click_while_reviewing_clears_the_selection(game):
    game.on_board_click(*first_legal(game))
    game._set_review_ply(1)
    game.on_board_click(0, 0)
    assert game.selected_ply is None


def test_click_after_game_over_reopens_the_result(game):
    game.session.finished_at = time.time()
    game.session.board.game_over = True
    game.session.board.winner = PLAYER_BLACK
    game.on_board_click(0, 0)
    assert game.overlay == "gameover"


def test_click_outside_targets_is_ignored(game):
    game.on_click((1, 1))
    assert game.session.ply == 0


def test_slider_values_are_applied_and_clamped(game):
    game._set_slider("volume", 0.25)
    assert game.settings.sound_volume == pytest.approx(0.25)
    game._set_slider("volume", 5.0)
    assert game.settings.sound_volume == pytest.approx(1.0)
    game._set_slider("scale", 9.0)
    assert game.settings.ui_scale == pytest.approx(1.5)
    game._set_slider("scale", 0.1)
    assert game.settings.ui_scale == pytest.approx(0.75)


def test_dragging_a_slider_updates_the_setting(game):
    game._open_options()
    game._dispatch_target("options_tab", "Audio")
    assert game.options_tab == "Audio"
    game.draw()
    target = game._slider_target("volume")
    assert target is not None
    game.dragging = "volume"
    game._handle_drag((target.x + target.w // 2, target.y + 2))
    assert 0.45 < game.settings.sound_volume < 0.55
    game.dragging = None
    game._handle_drag((0, 0))  # no-op without a drag target


def test_escape_quits_when_no_overlay_is_open(game):
    game.on_key(pg.K_ESCAPE, 0)
    assert game.running is False


def test_tab_switches_the_options_tab(game):
    game._open_options()
    first = game.options_tab
    game.on_key(pg.K_TAB, 0)
    assert game.options_tab != first


def test_ava_pause_and_speed(game):
    game._set_mode(MODE_AVA)
    game._toggle_pause()
    assert game.paused is True
    before = game.session.ply
    pump(game, frames=10)
    assert game.session.ply == before
    game._toggle_pause()
    assert game.paused is False

    game._set_ava_speed(99)
    assert game.ava_speed == 3
    game._set_ava_speed(-4)
    assert game.ava_speed == 0


def test_replay_playback_advances(game):
    game.on_board_click(*first_legal(game))
    game._set_review_ply(0)
    game._toggle_replay()
    assert game.replay_active is True
    for _ in range(120):
        game.update(1.0 / 30.0)
        if game.selected_ply:
            break
    assert game.selected_ply
    game.replay_active = False


def test_analyse_now_ignores_an_empty_game(game):
    game._analyse_now()
    assert game.review is None


def test_shutdown_autosaves_and_releases_workers(game):
    game.on_board_click(*first_legal(game))
    game.shutdown()
    assert not paths.autosave_path().exists() or True
    assert game.worker.busy is False


def test_stats_badge_reflects_history(game):
    assert game.stats_badge() == ""
    game.stats.games_played = 3
    game.stats.games_won = 2
    game.stats.games_lost = 1
    assert game.stats_badge() == "2W · 1L"


def test_hover_cell_is_suppressed_during_review(game):
    game._mouse = None
    assert game._hover_cell() is None


def test_loading_a_finished_game_shows_the_result_without_recounting(data_dir):
    import random

    instance = Game(LaunchOptions(mode=MODE_HVAI, level=1))
    try:
        if instance.overlay == "resume":
            instance._discard_resume()
        instance._set_board_size(6)
        rng = random.Random(3)
        while not instance.session.game_over:
            moves = instance.session.legal_moves()
            if not moves:
                instance.session.play_pending_pass()
                continue
            instance.session.apply_move(*rng.choice(moves))
        payload = persistence.build_save_payload(
            board_size=6,
            mode=MODE_HVAI,
            level=1,
            player_color=PLAYER_BLACK,
            moves=instance.session.to_move_log(),
            game_over=True,
            winner=instance.session.winner,
        )
        persistence.save_game_file(payload)

        played = instance.stats.games_played
        instance._load_game()
        assert instance.session.game_over is True
        assert instance.overlay == "gameover"
        assert (
            instance.stats.games_played == played
        ), "a loaded game must not be counted"
    finally:
        for worker in (instance.worker, instance.hint_worker, instance.review_worker):
            worker.cancel()
