"""Tests for themes, layout, animation, widgets and the keymap."""

from __future__ import annotations

import pygame as pg
import pytest

from iago.app.keymap import AI_VS_AI, PLAYING, REPLAY, bindings_by_context, lookup
from iago.ui.animation import (
    AnimatedValue,
    AnimationManager,
    ParticleSystem,
    ScreenShake,
    ToastStack,
    ease_out_back,
    ease_out_bounce,
    ease_out_cubic,
    ease_out_quad,
)
from iago.ui.assets import DiscCache, FontBook, mix, shade
from iago.ui.drawing import draw_bar, draw_panel, draw_star, gradient
from iago.ui.hud import format_clock
from iago.ui.layout import Rect, clamp_window, compute_layout
from iago.ui.theme import THEMES, THEME_ORDER, get_theme, next_theme
from iago.ui.widgets import Button, draw_segmented, draw_toggle

# ---------------------------------------------------------------------------
# Rect and layout
# ---------------------------------------------------------------------------


def test_rect_helpers():
    rect = Rect(10, 20, 100, 50)
    assert rect.right == 110
    assert rect.bottom == 70
    assert rect.center == (60, 45)
    assert rect.centery == 45
    assert rect.contains((10, 20))
    assert not rect.contains((110, 20))
    assert rect.inset(5) == Rect(15, 25, 90, 40)
    assert rect.moved(3, 4) == Rect(13, 24, 100, 50)
    assert tuple(rect) == (10, 20, 100, 50)
    assert len(rect) == 4
    assert rect[2] == 100


@pytest.mark.parametrize("size", [(760, 660), (1100, 800), (1600, 1000), (2400, 1500)])
@pytest.mark.parametrize("board_size", [6, 8, 10])
def test_layout_keeps_the_board_inside_the_window(size, board_size):
    layout = compute_layout(size, board_size)
    assert layout.board.x >= 0
    assert layout.board.y >= layout.menubar.bottom
    assert layout.board.right <= layout.width
    assert layout.board.bottom <= layout.status.y
    assert layout.board_px == layout.cell * board_size
    assert layout.cell >= 26


def test_layout_collapses_the_sidebar_on_narrow_windows():
    narrow = compute_layout((800, 700), 8)
    wide = compute_layout((1400, 900), 8)
    assert narrow.sidebar is None
    assert wide.sidebar is not None
    assert wide.sidebar.w > 200


def test_layout_hit_cell_round_trip():
    layout = compute_layout((1100, 800), 8)
    for row, col in ((0, 0), (3, 3), (7, 7)):
        assert layout.hit_cell(layout.cell_center(row, col)) == (row, col)
    assert layout.hit_cell((0, 0)) is None
    assert layout.hit_cell((layout.board.right + 5, layout.board.y)) is None


def test_clamp_window_enforces_minimums():
    assert clamp_window((10, 10)) == (760, 660)
    width, height = clamp_window((5000, 5000))
    assert width <= 2400 and height <= 1800


def test_layout_scale_multiplies_geometry():
    layout = compute_layout((1100, 800), 8)
    scaled = layout.scaled(2.0)
    assert scaled.cell == layout.cell * 2
    assert scaled.board.size == (layout.board.w * 2, layout.board.h * 2)


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


def test_theme_registry_is_complete():
    assert len(THEME_ORDER) >= 6
    for key in THEME_ORDER:
        theme = THEMES[key]
        assert theme.key == key
        assert theme.name
        assert theme.texture in ("felt", "wood", "linen", "none")
        assert theme.marker_style in ("dots", "shapes")
        for field_name in (
            "board_light",
            "board_dark",
            "grid_line",
            "frame",
            "black_body",
            "white_body",
            "background",
            "panel",
            "text",
            "accent",
        ):
            colour = getattr(theme, field_name)
            assert len(colour) == 3
            assert all(0 <= channel <= 255 for channel in colour)


def test_get_theme_falls_back_to_default():
    assert get_theme("does-not-exist").key == THEME_ORDER[0]


def test_next_theme_cycles():
    seen = {THEME_ORDER[0]}
    key = THEME_ORDER[0]
    for _ in range(len(THEME_ORDER) - 1):
        key = next_theme(key)
        seen.add(key)
    assert seen == set(THEME_ORDER)
    assert next_theme("nope") == THEME_ORDER[0]


def test_dark_and_light_discs_are_distinguishable():
    for theme in THEMES.values():
        black = sum(theme.black_body)
        white = sum(theme.white_body)
        assert abs(black - white) > 200


def test_colour_helpers():
    assert mix((0, 0, 0), (255, 255, 255), 0.5) == (127, 127, 127)
    assert shade((100, 100, 100), 2.0) == (200, 200, 200)
    assert shade((250, 250, 250), 2.0) == (255, 255, 255)
    assert shade((10, 10, 10), 0.0) == (0, 0, 0)


# ---------------------------------------------------------------------------
# Animation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "easing", [ease_out_quad, ease_out_cubic, ease_out_back, ease_out_bounce]
)
def test_easings_start_at_zero_and_end_near_one(easing):
    assert easing(0.0) == pytest.approx(0.0, abs=1e-6)
    assert easing(1.0) == pytest.approx(1.0, abs=1e-6)


def test_ease_out_back_overshoots():
    values = [ease_out_back(t / 20) for t in range(21)]
    assert max(values) > 1.0


def test_timeline_progress_and_delay():
    manager = AnimationManager()
    manager.add("key", started=10.0, duration=1.0, delay=0.5)
    assert manager.progress("key", 10.0) == 0.0
    assert manager.progress("key", 10.5) == 0.0
    assert manager.progress("key", 11.5) == pytest.approx(1.0)
    assert not manager.active("key", 12.0)
    assert manager.active("key", 10.7)
    assert manager.progress("missing", 5.0, default=0.42) == 0.42


def test_animation_manager_prunes():
    manager = AnimationManager()
    manager.add("a", 0.0, 0.1)
    manager.add("b", 0.0, 10.0)
    manager.prune(1.0)
    assert len(manager) == 1
    manager.clear()
    assert len(manager) == 0


def test_particles_lifecycle():
    system = ParticleSystem(limit=10)
    system.emit_burst(0, 0, (255, 255, 255), count=20)
    assert system.count == 10
    system.update(1.0)
    assert system.count == 0
    system.emit_confetti((0, 0, 100, 10), [(255, 0, 0)], count=5)
    assert system.count == 5
    system.clear()
    assert system.count == 0


def test_particles_draw_does_not_raise():
    pg.init()
    surface = pg.Surface((50, 50), pg.SRCALPHA)
    system = ParticleSystem()
    system.emit_burst(25, 25, (200, 200, 200), count=8)
    system.draw(surface)


def test_toast_stack_expires():
    stack = ToastStack()
    stack.push("hello", (255, 255, 255), now=0.0, duration=1.0)
    assert len(stack.active(0.1)) == 1
    assert stack.active(2.0) == []
    for index in range(6):
        stack.push(f"t{index}", (255, 255, 255), now=0.0, duration=5.0)
    assert len(stack.active(0.1)) == 3


def test_screen_shake_decays():
    shake = ScreenShake()
    shake.trigger(0.0, amplitude=10.0, duration=0.2)
    assert shake.offset(0.05) != (0, 0)
    assert shake.offset(0.5) == (0, 0)


def test_animated_value_approaches_target():
    value = AnimatedValue(0.0, rate=5.0)
    value.set(10.0)
    for _ in range(60):
        value.update(0.05)
    assert value.rounded == 10
    value.snap(3.0)
    assert value.rounded == 3


# ---------------------------------------------------------------------------
# Drawing and widgets
# ---------------------------------------------------------------------------


def test_gradient_is_cached_and_sized():
    pg.init()
    first = gradient((40, 20), (0, 0, 0), (255, 255, 255))
    second = gradient((40, 20), (0, 0, 0), (255, 255, 255))
    assert first is second
    assert first.get_size() == (40, 20)
    assert first.get_at((0, 0))[:3] == (0, 0, 0)
    assert first.get_at((0, 19))[:3] == (255, 255, 255)


def test_draw_primitives_do_not_raise():
    pg.init()
    surface = pg.Surface((200, 120))
    theme = get_theme("classic")
    draw_panel(surface, Rect(5, 5, 100, 60), theme)
    draw_star(surface, (50, 50), 12, (255, 255, 0))
    draw_bar(surface, Rect(10, 90, 180, 10), 0.4, theme, (0, 0, 0), (255, 255, 255))


def test_button_styles_and_disabled_state():
    theme = get_theme("classic")
    button = Button("k", "Go", Rect(0, 0, 80, 30), kind="primary")
    assert button.colors(theme)[0] == theme.accent
    button.enabled = False
    assert button.colors(theme)[0] != theme.accent


def test_segmented_control_returns_rects():
    pg.init()
    surface = pg.Surface((300, 60))
    theme = get_theme("classic")
    fonts = FontBook()
    rects = draw_segmented(
        surface, fonts, theme, Rect(0, 0, 300, 28), ["A", "B", "C"], 1
    )
    assert len(rects) == 3
    assert rects[1].x > rects[0].x


def test_toggle_returns_track():
    pg.init()
    surface = pg.Surface((300, 60))
    theme = get_theme("classic")
    fonts = FontBook()
    track = draw_toggle(surface, fonts, theme, Rect(0, 0, 300, 30), "Sound", True)
    assert track.right == 300


def test_disc_cache_reuses_surfaces():
    pg.init()
    cache = DiscCache()
    theme = get_theme("classic")
    first = cache.get(theme, 1, 20)
    second = cache.get(theme, 1, 20)
    assert first is second
    assert first.get_size()[0] > 40
    ghost = cache.ghost(theme, 2, 20)
    assert ghost is not first
    cache.clear()
    assert cache.get(theme, 1, 20) is not first


def test_font_book_renders_and_caches():
    pg.init()
    fonts = FontBook()
    surface = fonts.render("Hello", "body", (255, 255, 255))
    assert surface.get_width() > 0
    assert fonts.render("Hello", "body", (255, 255, 255)) is surface
    assert fonts.measure("Hello", "body")[0] > 0


# ---------------------------------------------------------------------------
# Keymap and formatting
# ---------------------------------------------------------------------------


def test_keymap_lookup_prefers_modifiers():
    assert lookup(pg.K_s, pg.KMOD_CTRL) == "save"
    assert lookup(pg.K_s, 0) == "save"
    assert lookup(pg.K_z, pg.KMOD_CTRL) == "undo"
    assert lookup(pg.K_z, pg.KMOD_CTRL | pg.KMOD_SHIFT) == "redo"


def test_keymap_contexts():
    assert lookup(pg.K_SPACE, 0, PLAYING) == "hint"
    assert lookup(pg.K_SPACE, 0, REPLAY) == "replay_toggle"
    assert lookup(pg.K_p, 0, AI_VS_AI) == "pause"
    assert lookup(pg.K_p, 0, PLAYING) is None


def test_keymap_is_grouped():
    grouped = bindings_by_context()
    assert PLAYING in grouped
    assert all(binding.display and binding.label for binding in grouped[PLAYING])


def test_format_clock():
    assert format_clock(None) == "--:--"
    assert format_clock(0) == "00:00"
    assert format_clock(65) == "01:05"
    assert format_clock(3725) == "1:02:05"
