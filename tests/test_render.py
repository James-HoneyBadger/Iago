"""Headless rendering smoke tests across themes, sizes and overlays."""

from __future__ import annotations

import pytest

from iago.app.analysis import analyse_moves
from iago.app.session import Session
from iago.app.settings import GameSettings, GameStats, LevelRecord
from iago.core.constants import PLAYER_BLACK
from iago.ui.overlays import GameOverData, OptionsData, ResumeData
from iago.ui.renderer import RenderModel, Renderer
from iago.ui.theme import THEME_ORDER, get_theme


def make_session(moves: int = 6) -> Session:
    session = Session(size=8, mode="hvai", player_color=PLAYER_BLACK, level=2)
    for _ in range(moves):
        options = session.legal_moves()
        if not options:
            session.play_pending_pass()
            continue
        session.apply_move(*options[0])
    return session


def board_colours(renderer: Renderer) -> set[tuple[int, int, int]]:
    layout = renderer.layout
    colours = set()
    for row in range(layout.board_size):
        for col in range(layout.board_size):
            x, y = layout.cell_center(row, col)
            colours.add(tuple(renderer.surface.get_at((x, y)))[:3])
    return colours


@pytest.mark.parametrize("theme_key", THEME_ORDER)
def test_render_every_theme(theme_key):
    theme = get_theme(theme_key)
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session()
    model = RenderModel(
        session=session,
        theme=theme,
        hint_move=session.legal_moves()[0] if session.legal_moves() else None,
        hover_cell=(3, 3),
        mouse=(60, 60),
    )
    renderer.draw(model, now=2.0)
    assert renderer.surface.get_size() == (
        renderer.layout.width,
        renderer.layout.height,
    )
    assert len(board_colours(renderer)) > 1


@pytest.mark.parametrize("board_size", [6, 8, 10])
def test_render_every_board_size(board_size):
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), board_size, theme)
    session = Session(size=board_size, mode="hvh")
    session.apply_move(*session.legal_moves()[0])
    renderer.draw(RenderModel(session=session, theme=theme), now=1.0)
    assert renderer.layout.board_size == board_size
    assert renderer.layout.board_px == renderer.layout.cell * board_size


def test_small_window_hides_the_sidebar():
    theme = get_theme("classic")
    renderer = Renderer((800, 700), 8, theme)
    session = make_session(2)
    renderer.draw(RenderModel(session=session, theme=theme), now=1.0)
    assert renderer.layout.sidebar is None
    assert renderer.sidebar_hit is None


def test_render_with_animations_mid_flight():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = Session(mode="hvh")
    session.apply_move(2, 3)
    record = session.records[-1]
    renderer.animate_move(record, now=10.0)
    for now in (10.0, 10.05, 10.1, 10.2, 11.0):
        renderer.update(0.02, now=now)
        renderer.draw(RenderModel(session=session, theme=theme), now=now)
    assert renderer.particles.count >= 0


def test_options_overlay_registers_click_targets():
    theme = get_theme("midnight")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(2)
    model = RenderModel(
        session=session,
        theme=theme,
        overlay="options",
        overlay_data=OptionsData(GameSettings(), tab="Game"),
    )
    renderer.draw(model, now=1.0)
    actions = {target.action for target in renderer.targets}
    assert "options_tab" in actions
    assert "button" in actions
    assert "set_theme" not in actions

    model.overlay_data = OptionsData(GameSettings(), tab="Appearance")
    renderer.draw(model, now=1.0)
    actions = {target.action for target in renderer.targets}
    assert "set_theme" in actions
    assert "toggle" in actions


def test_help_and_stats_overlays_render():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(3)
    stats = GameStats(
        games_played=4, games_won=2, by_level={2: LevelRecord(played=4, won=2)}
    )
    renderer.draw(RenderModel(session=session, theme=theme, overlay="help"), now=1.0)
    renderer.draw(
        RenderModel(session=session, theme=theme, overlay="stats", stats=stats), now=1.0
    )
    assert any(target.action == "close_overlay" for target in renderer.targets)


def test_game_over_overlay_with_review():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(8)
    review = analyse_moves(session.to_move_log(), depth=1)
    data = GameOverData(session=session, review=review, review_progress=(8, 8))
    renderer.draw(
        RenderModel(
            session=session, theme=theme, overlay="gameover", overlay_data=data
        ),
        now=1.0,
    )
    values = {target.value for target in renderer.targets if target.action == "button"}
    assert {"rematch", "review", "stats", "close"} <= values


def test_resume_overlay_renders():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(1)
    data = ResumeData(move_count=12, mode="Human vs AI", level="Expert")
    renderer.draw(
        RenderModel(session=session, theme=theme, overlay="resume", overlay_data=data),
        now=1.0,
    )
    values = {target.value for target in renderer.targets if target.action == "button"}
    assert {"resume", "discard"} <= values


def test_menubar_hit_testing():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(2)
    renderer.draw(RenderModel(session=session, theme=theme), now=1.0)
    button = renderer.menubar_buttons[0]
    target = renderer.hit_test(button.rect.center)
    assert target is not None
    assert target.action == "button"
    assert target.value == "new_game"
    assert renderer.hit_test((5, renderer.layout.height - 2)) is None


def test_sidebar_rows_are_clickable():
    theme = get_theme("classic")
    renderer = Renderer((1400, 900), 8, theme)
    session = make_session(4)
    renderer.draw(RenderModel(session=session, theme=theme), now=1.0)
    assert renderer.sidebar_hit is not None
    rect, ply = renderer.sidebar_hit.rows[0]
    target = renderer.hit_test(rect.center)
    assert target is not None
    assert target.action == "sidebar_ply"
    assert target.value == ply


def test_theme_and_scale_changes_invalidate_caches():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(2)
    renderer.draw(RenderModel(session=session, theme=theme), now=1.0)
    first_plate = renderer._plate_surface(True)
    renderer.set_theme(get_theme("ocean"))
    assert renderer._plate_surface(True) is not first_plate

    renderer.set_board_size(10)
    assert renderer.layout.board_size == 10

    renderer.set_ui_scale(1.25)
    assert renderer.ui_scale == pytest.approx(1.25)
    assert renderer.fonts.scale == pytest.approx(1.25)


def test_resize_updates_layout():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    renderer.resize((1500, 1000))
    assert renderer.layout.width == 1500
    assert renderer.layout.height == 1000


def test_debug_overlay_renders():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(2)
    renderer.draw(
        RenderModel(session=session, theme=theme, debug=True, fps=59.4), now=1.0
    )


def test_display_board_override_renders_historical_position():
    theme = get_theme("classic")
    renderer = Renderer((1100, 800), 8, theme)
    session = make_session(4)
    past = session.position_at(1)
    renderer.draw(
        RenderModel(session=session, theme=theme, display_board=past, selected_ply=1),
        now=1.0,
    )
