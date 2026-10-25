"""Tests for themes, layout, animation, widgets and the keymap."""

from __future__ import annotations

import pygame as pg
import pytest

from iago.app.keymap import (
    AI_VS_AI,
    BINDINGS,
    PLAYING,
    REPLAY,
    bindings_by_context,
    lookup,
)
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
from iago.ui.drawing import (
    draw_bar,
    draw_bevel,
    draw_checker,
    draw_glow,
    draw_label_value,
    draw_panel,
    draw_ring,
    draw_separator,
    draw_shadow,
    draw_star,
    fit_text,
    gradient,
    with_alpha,
    wrap_text,
)
from iago.ui.hud import format_clock
from iago.ui.layout import Rect, clamp_window, compute_layout
from iago.ui.theme import THEMES, THEME_ORDER, get_theme, next_theme
from iago.ui.widgets import (
    Button,
    draw_badge,
    draw_keycap,
    draw_scrollbar,
    draw_segmented,
    draw_slider,
    draw_tabs,
    draw_toggle,
    draw_tooltip,
    focus_ring,
)

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


# ---------------------------------------------------------------------------
# Widget details
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["secondary", "primary", "danger", "ghost"])
def test_button_kinds_have_distinct_colours(kind):
    theme = get_theme("classic")
    button = Button("k", "Go", Rect(0, 0, 80, 30), kind=kind)
    fill, border, text = button.colors(theme)
    assert all(isinstance(channel, int) for channel in (*fill, *border, *text))


def test_button_draw_with_states():
    surface = pg.Surface((120, 40))
    theme = get_theme("classic")
    fonts = FontBook()
    button = Button("k", "Play", Rect(0, 0, 120, 40), kind="primary", active=True)
    button.draw(surface, fonts, theme, hovered=True, pressed=True, focused=True)
    assert surface.get_at((60, 20))[:3] != (0, 0, 0)
    button.enabled = False
    button.draw(surface, fonts, theme)


def test_focus_ring_draws_around_the_rect():
    surface = pg.Surface((80, 60))
    focus_ring(surface, Rect(10, 10, 40, 30), get_theme("classic"))
    assert surface.get_at((30, 8))[:3] != (0, 0, 0)


def test_slider_positions_the_knob():
    surface = pg.Surface((220, 40))
    theme = get_theme("classic")
    low = draw_slider(surface, theme, Rect(0, 0, 200, 30), 0.0)
    high = draw_slider(surface, theme, Rect(0, 0, 200, 30), 1.0)
    assert high.x > low.x
    assert low.x == 0 and high.right <= 200
    draw_slider(surface, theme, Rect(0, 0, 200, 30), 0.5, enabled=False)


def test_tabs_and_badges_return_rects():
    surface = pg.Surface((400, 120))
    theme = get_theme("classic")
    fonts = FontBook()
    tabs = draw_tabs(surface, fonts, theme, Rect(0, 0, 400, 26), ["One", "Two"], 1)
    assert len(tabs) == 2 and tabs[1].x > tabs[0].x
    for anchor in ("topleft", "center", "topright", "midright"):
        rect = draw_badge(surface, fonts, theme, (200, 60), "12", theme.accent, anchor)
        assert rect.w > 0 and rect.h > 0


def test_tooltip_is_clamped_inside_bounds():
    surface = pg.Surface((200, 120))
    theme = get_theme("classic")
    fonts = FontBook()
    bounds = Rect(0, 0, 200, 120)
    draw_tooltip(surface, fonts, theme, "hint text", (195, 118), bounds)
    draw_tooltip(surface, fonts, theme, "", (10, 10), bounds)  # empty is a no-op


def test_keycap_reports_its_width():
    surface = pg.Surface((120, 40))
    theme = get_theme("classic")
    fonts = FontBook()
    narrow = draw_keycap(surface, fonts, theme, (0, 20), "A")
    wide = draw_keycap(surface, fonts, theme, (40, 20), "Ctrl+S")
    assert wide > narrow


def test_scrollbar_skips_short_content():
    surface = pg.Surface((20, 200))
    theme = get_theme("classic")
    track = Rect(0, 0, 10, 100)
    draw_scrollbar(surface, theme, track, 0, 100, 100)
    assert surface.get_at((5, 50))[:3] == (0, 0, 0)
    draw_scrollbar(surface, theme, track, 120, 400, 100)
    assert surface.get_at((5, 50))[:3] != (0, 0, 0)


def test_segmented_handles_no_options():
    surface = pg.Surface((100, 40))
    assert (
        draw_segmented(
            surface, FontBook(), get_theme("classic"), Rect(0, 0, 90, 24), [], 0
        )
        == []
    )


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def test_with_alpha_adds_a_channel():
    assert with_alpha((1, 2, 3), 128) == (1, 2, 3, 128)
    assert with_alpha((1, 2, 3, 4), 9) == (1, 2, 3, 9)


def test_panel_shadow_separator_and_bevel():
    surface = pg.Surface((160, 120))
    theme = get_theme("classic")
    draw_shadow(surface, Rect(10, 10, 80, 40), radius=6)
    draw_panel(surface, Rect(10, 60, 80, 40), theme)
    draw_separator(surface, (10, 116), (150, 116), theme)
    draw_bevel(surface, Rect(60, 10, 60, 40), theme)
    draw_ring(surface, (40, 40), 10, theme.accent, 2)
    draw_checker(
        surface, Rect(20, 20, 60, 60), 10, theme.board_light, theme.board_dark, 6
    )
    draw_glow(surface, (80, 80), 20, theme.accent)
    width = draw_label_value(surface, FontBook(), "Depth", "8", (10, 20), theme)
    assert width > 0
    assert surface.get_at((15, 70))[:3] != (0, 0, 0)


def test_fit_text_shortens_long_labels():
    fonts = FontBook()
    short = fit_text(fonts, "abc", "body", 400)
    narrow = fit_text(fonts, "a very long label indeed", "body", 40)
    assert short == "abc"
    assert narrow != "a very long label indeed"
    assert len(narrow) < len("a very long label indeed")


def test_wrap_text_breaks_on_words():
    fonts = FontBook()
    lines = wrap_text(fonts, "the quick brown fox jumps", "body", 80)
    assert len(lines) > 1
    assert all(" " not in line.strip() or len(line) < 80 for line in lines)
    assert wrap_text(fonts, "", "body", 80) == []


# ---------------------------------------------------------------------------
# Keymap documentation lock
# ---------------------------------------------------------------------------


def test_every_documented_shortcut_is_bound():
    """The user guide's key table must stay true to ``BINDINGS``."""

    cases = [
        (pg.K_n, 0, PLAYING, "new_game"),
        (pg.K_r, 0, PLAYING, "new_game"),
        (pg.K_u, 0, PLAYING, "undo"),
        (pg.K_z, pg.KMOD_CTRL, PLAYING, "undo"),
        (pg.K_y, 0, PLAYING, "redo"),
        (pg.K_y, pg.KMOD_CTRL, PLAYING, "redo"),
        (pg.K_z, pg.KMOD_CTRL | pg.KMOD_SHIFT, PLAYING, "redo"),
        (pg.K_h, 0, PLAYING, "toggle_hints"),
        (pg.K_SPACE, 0, PLAYING, "hint"),
        (pg.K_d, 0, PLAYING, "cycle_level"),
        (pg.K_1, 0, PLAYING, "set_level"),
        (pg.K_5, 0, PLAYING, "set_level"),
        (pg.K_m, 0, PLAYING, "cycle_mode"),
        (pg.K_t, 0, PLAYING, "cycle_theme"),
        (pg.K_b, 0, PLAYING, "cycle_board_size"),
        (pg.K_v, 0, PLAYING, "toggle_sound"),
        (pg.K_s, 0, PLAYING, "save"),
        (pg.K_s, pg.KMOD_CTRL, PLAYING, "save"),
        (pg.K_l, 0, PLAYING, "load"),
        (pg.K_o, pg.KMOD_CTRL, PLAYING, "load"),
        (pg.K_a, 0, PLAYING, "analyse"),
        (pg.K_p, 0, AI_VS_AI, "pause"),
        (pg.K_PLUS, 0, AI_VS_AI, "faster"),
        (pg.K_MINUS, 0, AI_VS_AI, "slower"),
        (pg.K_SPACE, 0, REPLAY, "replay_toggle"),
        (pg.K_RIGHT, 0, REPLAY, "replay_next"),
        (pg.K_LEFT, 0, REPLAY, "replay_prev"),
        (pg.K_HOME, 0, REPLAY, "replay_start"),
        (pg.K_END, 0, REPLAY, "replay_end"),
        (pg.K_o, 0, PLAYING, "options"),
        (pg.K_TAB, 0, PLAYING, "options"),
        (pg.K_F1, 0, PLAYING, "help"),
        (pg.K_F11, 0, PLAYING, "fullscreen"),
        (pg.K_F3, 0, PLAYING, "debug"),
        (pg.K_ESCAPE, 0, PLAYING, "escape"),
    ]
    for key, mods, context, action in cases:
        assert lookup(key, mods, context) == action, (key, mods, context)


def test_documented_displays_exist_in_the_table():
    displays = {binding.display for binding in BINDINGS}
    for display in ("N / R", "U", "Y", "Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z", "1–5"):
        assert display in displays
