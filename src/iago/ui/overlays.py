"""Modal overlays: options, help, statistics, game over and resume."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import pygame as pg

from ..ai.levels import MAX_DIFFICULTY, get_level
from ..app.achievements import ACHIEVEMENTS, progress as achievement_progress
from ..app.analysis import BLUNDER, INACCURACY, MISTAKE, GameReview
from ..app.keymap import bindings_by_context
from ..app.session import Session
from ..app.settings import GameSettings, GameStats
from ..branding import APP_NAME, VERSION
from ..core.constants import MODE_LABELS, PLAYER_BLACK, PLAYER_WHITE
from .assets import FontBook, shade
from .drawing import draw_bar, draw_panel, draw_text, fit_text
from .hud import format_clock
from .layout import MAX_UI_SCALE, MIN_UI_SCALE, Layout, Rect, centered_panel
from .theme import THEMES, THEME_ORDER, Theme
from .widgets import Button, draw_segmented, draw_slider, draw_tabs, draw_toggle

OPTION_TABS = ("Game", "Appearance", "Audio", "Controls")


@dataclass
class ClickTarget:
    """A clickable region produced while drawing an overlay."""

    rect: Rect
    action: str
    value: Any = None
    tooltip: str = ""


@dataclass
class OptionsData:
    settings: GameSettings
    tab: str = "Game"
    mouse: Optional[Tuple[int, int]] = None
    dragging: Optional[str] = None


@dataclass
class GameOverData:
    session: Session
    reason: str = "board"
    review: Optional[GameReview] = None
    review_progress: Tuple[int, int] = (0, 0)
    achievements: Sequence[str] = ()
    selected_ply: Optional[int] = None


@dataclass
class ResumeData:
    move_count: int = 0
    mode: str = MODE_LABELS["hvai"]
    level: str = ""
    played_at: str = ""


def _scrim(surface: pg.Surface, layout: Layout, alpha: int = 190) -> None:
    overlay = pg.Surface((layout.width, layout.height), pg.SRCALPHA)
    overlay.fill((0, 0, 0, alpha))
    surface.blit(overlay, (0, 0))


def _panel(layout: Layout, width: int, height: int) -> Rect:
    scale = layout.ui_scale
    return centered_panel(layout, int(width * scale), int(height * scale))


def _modal_header(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    panel: Rect,
    title: str,
    subtitle: str = "",
) -> Rect:
    draw_text(
        surface,
        fonts,
        title,
        (panel.x + 22, panel.y + 16),
        "title",
        theme.text,
        bold=True,
    )
    if subtitle:
        draw_text(
            surface,
            fonts,
            subtitle,
            (panel.x + 22, panel.y + 48),
            "small",
            theme.text_dim,
        )
    close = Rect(panel.right - 40, panel.y + 14, 26, 26)
    pg.draw.rect(surface, theme.panel_raised, close.as_tuple(), border_radius=6)
    draw_text(
        surface, fonts, "✕", close.center, "small", theme.text_dim, anchor="center"
    )
    return close


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


def draw_options(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    data: OptionsData,
) -> List[ClickTarget]:
    scale = layout.ui_scale
    _scrim(surface, layout)
    panel = _panel(layout, 620, 560)
    draw_panel(surface, panel, theme, radius=int(14 * scale))

    close = _modal_header(
        surface,
        fonts,
        theme,
        panel,
        "Options",
        f"{APP_NAME} {VERSION}",
    )
    targets: List[ClickTarget] = [ClickTarget(close, "close_overlay")]

    tab_rect = Rect(
        panel.x + 18, panel.y + int(74 * scale), panel.w - 36, int(30 * scale)
    )
    tabs = draw_tabs(
        surface,
        fonts,
        theme,
        tab_rect,
        OPTION_TABS,
        OPTION_TABS.index(data.tab) if data.tab in OPTION_TABS else 0,
    )
    for index, rect in enumerate(tabs):
        targets.append(ClickTarget(rect, "options_tab", OPTION_TABS[index]))

    content = Rect(
        panel.x + int(18 * scale),
        tab_rect.bottom + int(10 * scale),
        panel.w - int(36 * scale),
        panel.h - int(170 * scale),
    )
    if data.tab == "Game":
        targets += _options_game(surface, fonts, theme, content, data, scale)
    elif data.tab == "Appearance":
        targets += _options_appearance(surface, fonts, theme, content, data, scale)
    elif data.tab == "Audio":
        targets += _options_audio(surface, fonts, theme, content, data, scale)
    else:
        targets += _options_controls(surface, fonts, theme, content, scale)

    footer = Rect(
        panel.x + int(18 * scale),
        panel.bottom - int(54 * scale),
        panel.w - int(36 * scale),
        int(34 * scale),
    )
    buttons = [
        Button(
            "new_game",
            "New Game",
            Rect(footer.x, footer.y, int(120 * scale), footer.h),
            "primary",
        ),
        Button(
            "close",
            "Close",
            Rect(footer.right - int(120 * scale), footer.y, int(120 * scale), footer.h),
        ),
    ]
    for button in buttons:
        hovered = data.mouse is not None and button.rect.contains(data.mouse)
        button.draw(surface, fonts, theme, hovered=hovered, radius=int(6 * scale))
        targets.append(ClickTarget(button.rect, "button", button.key))
    return targets


def _row_label(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    label: str,
    hint: str = "",
) -> None:
    draw_text(
        surface,
        fonts,
        label,
        (rect.x, rect.centery),
        "small",
        theme.text,
        anchor="midleft",
    )
    if hint:
        draw_text(
            surface,
            fonts,
            fit_text(fonts, hint, "tiny", rect.w - 150),
            (rect.right, rect.centery),
            "tiny",
            theme.text_dim,
            anchor="midright",
        )


def _options_game(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    content: Rect,
    data: OptionsData,
    scale: float,
) -> List[ClickTarget]:
    settings = data.settings
    targets: List[ClickTarget] = []
    rows = _row_rects(content, 5, scale)
    label_w = int(150 * scale)

    def control(row: Rect) -> Rect:
        return Rect(row.x + label_w, row.y, row.w - label_w, int(28 * scale)).moved(
            0, -int(2 * scale)
        )

    # Mode
    row = rows[0]
    _row_label(
        surface, fonts, theme, Rect(row.x, row.centery - 12, label_w, 24), "Mode"
    )
    modes = [MODE_LABELS[mode] for mode in ("hvai", "hvh", "ava")]
    active = {"hvai": 0, "hvh": 1, "ava": 2}.get(settings.mode, 0)
    rects = draw_segmented(
        surface, fonts, theme, control(row), modes, active, scale=scale
    )
    for index, rect in enumerate(rects):
        targets.append(ClickTarget(rect, "set_mode", ("hvai", "hvh", "ava")[index]))

    # Difficulty
    row = rows[1]
    _row_label(
        surface, fonts, theme, Rect(row.x, row.centery - 12, label_w, 24), "Difficulty"
    )
    names = [get_level(level).name for level in range(1, MAX_DIFFICULTY + 1)]
    rects = draw_segmented(
        surface, fonts, theme, control(row), names, settings.ai_level - 1, scale=scale
    )
    for index, rect in enumerate(rects):
        targets.append(ClickTarget(rect, "set_level", index + 1))

    # Play as
    row = rows[2]
    _row_label(
        surface, fonts, theme, Rect(row.x, row.centery - 12, label_w, 24), "Play as"
    )
    rects = draw_segmented(
        surface,
        fonts,
        theme,
        control(row),
        ["Black", "White"],
        settings.player_color - 1,
        enabled=settings.mode == "hvai",
        scale=scale,
    )
    for index, rect in enumerate(rects):
        targets.append(ClickTarget(rect, "set_color", index + 1))

    # Board size
    row = rows[3]
    _row_label(
        surface, fonts, theme, Rect(row.x, row.centery - 12, label_w, 24), "Board size"
    )
    sizes = (6, 8, 10)
    active = sizes.index(settings.board_size) if settings.board_size in sizes else 1
    rects = draw_segmented(
        surface,
        fonts,
        theme,
        control(row),
        [f"{size}×{size}" for size in sizes],
        active,
        scale=scale,
    )
    for index, rect in enumerate(rects):
        targets.append(ClickTarget(rect, "set_board_size", sizes[index]))

    # Clock
    row = rows[4]
    _row_label(
        surface, fonts, theme, Rect(row.x, row.centery - 12, label_w, 24), "Clock"
    )
    options = ["Off", "Stopwatch", "Blitz 5+3", "Blitz 10+0"]
    active = {"off": 0, "stopwatch": 1, "blitz": 2}.get(settings.clock_mode, 0)
    if settings.clock_mode == "blitz" and settings.blitz_minutes >= 10:
        active = 3
    rects = draw_segmented(
        surface, fonts, theme, control(row), options, active, scale=scale
    )
    values = [("off", 5, 3), ("stopwatch", 5, 3), ("blitz", 5, 3), ("blitz", 10, 0)]
    for index, rect in enumerate(rects):
        targets.append(ClickTarget(rect, "set_clock", values[index]))

    return targets


def _options_appearance(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    content: Rect,
    data: OptionsData,
    scale: float,
) -> List[ClickTarget]:
    settings = data.settings
    targets: List[ClickTarget] = []
    draw_text(surface, fonts, "Theme", (content.x, content.y), "small", theme.text)
    grid_top = content.y + int(22 * scale)
    columns = 4
    gap = int(6 * scale)
    cell_w = (content.w - gap * (columns - 1)) // columns
    cell_h = int(58 * scale)
    for index, key in enumerate(THEME_ORDER):
        option = THEMES[key]
        row, col = divmod(index, columns)
        cell = Rect(
            content.x + col * (cell_w + gap),
            grid_top + row * (cell_h + gap),
            cell_w,
            cell_h,
        )
        selected = settings.theme == key
        pg.draw.rect(surface, option.board_light, cell.as_tuple(), border_radius=6)
        pg.draw.circle(
            surface,
            option.black_body,
            (cell.x + int(16 * scale), cell.centery),
            int(8 * scale),
        )
        pg.draw.circle(
            surface,
            option.white_body,
            (cell.x + int(34 * scale), cell.centery),
            int(8 * scale),
        )
        draw_text(
            surface,
            fonts,
            fit_text(fonts, option.name, "tiny", cell.w - 52),
            (cell.right - int(6 * scale), cell.centery),
            "tiny",
            theme.text_inverse,
            anchor="midright",
            bold=True,
        )
        if selected:
            draw_rect = pg.Rect(cell.as_tuple())
            pg.draw.rect(surface, theme.accent, draw_rect, 2, border_radius=6)
        targets.append(ClickTarget(cell, "set_theme", key))

    toggles_top = grid_top + 2 * (cell_h + gap) + int(8 * scale)
    scale_row_h = int(30 * scale)
    toggles_area = Rect(
        content.x,
        toggles_top,
        content.w,
        max(
            int(120 * scale),
            content.bottom - toggles_top - scale_row_h - int(8 * scale),
        ),
    )
    rows = _row_rects(toggles_area, 4, scale)
    for toggle_row, (key, label, value) in zip(
        rows,
        (
            ("animations", "Animations", settings.animations),
            ("particles", "Particles", settings.particles),
            ("coordinates", "Coordinates", settings.show_coordinates),
            ("eval_bar", "Evaluation bar", settings.show_eval_bar),
        ),
    ):
        track = draw_toggle(surface, fonts, theme, toggle_row, label, value)
        targets.append(ClickTarget(track, "toggle", key))
        targets.append(ClickTarget(toggle_row, "toggle", key))

    scale_row = Rect(
        content.x,
        toggles_area.bottom + int(8 * scale),
        content.w,
        scale_row_h,
    )
    draw_text(
        surface,
        fonts,
        "Interface scale",
        (scale_row.x, scale_row.centery),
        "small",
        theme.text,
        anchor="midleft",
    )
    slider = Rect(
        scale_row.x + int(150 * scale),
        scale_row.centery - 10,
        scale_row.w - int(210 * scale),
        20,
    )
    span = MAX_UI_SCALE - MIN_UI_SCALE
    position = (settings.ui_scale - MIN_UI_SCALE) / span if span else 0.0
    draw_slider(surface, theme, slider, position)
    draw_text(
        surface,
        fonts,
        f"{settings.ui_scale:.2f}×",
        (scale_row.right, scale_row.centery),
        "small",
        theme.text_dim,
        anchor="midright",
    )
    targets.append(ClickTarget(slider, "slider_scale"))
    return targets


def _options_audio(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    content: Rect,
    data: OptionsData,
    scale: float,
) -> List[ClickTarget]:
    settings = data.settings
    targets: List[ClickTarget] = []
    rows = _row_rects(content, 3, scale)

    track = draw_toggle(
        surface, fonts, theme, rows[0], "Sound effects", settings.sound_enabled
    )
    targets.append(ClickTarget(track, "toggle", "sound"))
    targets.append(ClickTarget(rows[0], "toggle", "sound"))

    volume_row = rows[1]
    draw_text(
        surface,
        fonts,
        "Volume",
        (volume_row.x, volume_row.centery),
        "small",
        theme.text,
        anchor="midleft",
    )
    slider = Rect(
        volume_row.x + int(150 * scale),
        volume_row.centery - 10,
        volume_row.w - int(210 * scale),
        20,
    )
    draw_slider(
        surface, theme, slider, settings.sound_volume, enabled=settings.sound_enabled
    )
    draw_text(
        surface,
        fonts,
        f"{int(settings.sound_volume * 100)}%",
        (volume_row.right, volume_row.centery),
        "small",
        theme.text_dim,
        anchor="midright",
    )
    targets.append(ClickTarget(slider, "slider_volume"))

    test_rect = Rect(rows[2].x, rows[2].y, int(130 * scale), int(30 * scale))
    button = Button(
        "test_sound", "Play test", test_rect, enabled=settings.sound_enabled
    )
    hovered = data.mouse is not None and button.rect.contains(data.mouse)
    button.draw(surface, fonts, theme, hovered=hovered, radius=int(6 * scale))
    targets.append(ClickTarget(test_rect, "test_sound"))
    return targets


def _options_controls(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    content: Rect,
    scale: float,
) -> List[ClickTarget]:
    grouped = bindings_by_context()
    column_width = content.w // 2
    columns = [
        ("Playing",),
        ("Global", "AI vs AI", "Replay"),
    ]
    line_height = int(20 * scale)
    for column_index, contexts in enumerate(columns):
        x = content.x + column_index * column_width
        y = content.y
        for context in contexts:
            bindings = grouped.get(context, [])
            if not bindings:
                continue
            draw_text(
                surface,
                fonts,
                context.upper(),
                (x, y),
                "tiny",
                theme.accent_soft,
                bold=True,
            )
            y += line_height
            for binding in bindings:
                key_surface = fonts.render(binding.display, "tiny", theme.text)
                box = Rect(x, y, key_surface.get_width() + 10, line_height - 4)
                pg.draw.rect(
                    surface, theme.panel_raised, box.as_tuple(), border_radius=3
                )
                pg.draw.rect(
                    surface, theme.panel_border, box.as_tuple(), 1, border_radius=3
                )
                surface.blit(
                    key_surface,
                    (
                        box.centerx - key_surface.get_width() // 2,
                        box.centery - key_surface.get_height() // 2,
                    ),
                )
                draw_text(
                    surface,
                    fonts,
                    fit_text(fonts, binding.label, "tiny", column_width - box.w - 18),
                    (box.right + 8, box.centery),
                    "tiny",
                    theme.text_dim,
                    anchor="midleft",
                )
                y += line_height
            y += int(6 * scale)
    return []


def _row_rects(area: Rect, count: int, scale: float) -> List[Rect]:
    height = max(int(34 * scale), min(int(46 * scale), area.h // max(1, count)))
    return [
        Rect(area.x, area.y + index * height, area.w, height) for index in range(count)
    ]


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def draw_help(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
) -> List[ClickTarget]:
    scale = layout.ui_scale
    _scrim(surface, layout)
    panel = _panel(layout, 660, 560)
    draw_panel(surface, panel, theme, radius=int(14 * scale))
    close = _modal_header(
        surface,
        fonts,
        theme,
        panel,
        "Controls",
        "Everything you can do, at a glance",
    )
    targets = [ClickTarget(close, "close_overlay")]

    _options_controls(
        surface,
        fonts,
        theme,
        Rect(
            panel.x + int(20 * scale),
            panel.y + int(80 * scale),
            panel.w - int(40 * scale),
            panel.h - int(100 * scale),
        ),
        scale,
    )

    footer = Rect(
        panel.x + int(20 * scale),
        panel.bottom - int(48 * scale),
        panel.w - int(40 * scale),
        int(30 * scale),
    )
    draw_text(
        surface,
        fonts,
        "Tip: click a move in the sidebar to review that position.",
        (footer.x, footer.centery),
        "tiny",
        theme.text_dim,
        anchor="midleft",
    )
    return targets


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def draw_stats(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    stats: GameStats,
) -> List[ClickTarget]:
    scale = layout.ui_scale
    _scrim(surface, layout)
    panel = _panel(layout, 660, 580)
    draw_panel(surface, panel, theme, radius=int(14 * scale))
    close = _modal_header(
        surface, fonts, theme, panel, "Statistics", "Your record so far"
    )
    targets = [ClickTarget(close, "close_overlay")]

    cards = [
        ("Games", str(stats.games_played)),
        ("Won", str(stats.games_won)),
        ("Win rate", f"{stats.win_rate * 100:.0f}%"),
        ("Best score", str(stats.best_score)),
        ("Win streak", str(stats.win_streak)),
    ]
    card_w = (panel.w - int(56 * scale)) // len(cards)
    for index, (label, value) in enumerate(cards):
        card = Rect(
            panel.x + int(20 * scale) + index * card_w,
            panel.y + int(80 * scale),
            card_w - int(8 * scale),
            int(64 * scale),
        )
        pg.draw.rect(surface, theme.panel_raised, card.as_tuple(), border_radius=8)
        draw_text(
            surface,
            fonts,
            value,
            (card.centerx, card.y + int(22 * scale)),
            "title",
            theme.accent,
            anchor="center",
            bold=True,
        )
        draw_text(
            surface,
            fonts,
            label,
            (card.centerx, card.bottom - int(14 * scale)),
            "tiny",
            theme.text_dim,
            anchor="center",
        )

    table_top = panel.y + int(160 * scale)
    draw_text(
        surface,
        fonts,
        "BY DIFFICULTY",
        (panel.x + int(20 * scale), table_top),
        "tiny",
        theme.accent_soft,
        bold=True,
    )
    row_y = table_top + int(18 * scale)
    for level in range(1, MAX_DIFFICULTY + 1):
        record = stats.by_level.get(level)
        name = get_level(level).name
        draw_text(
            surface,
            fonts,
            name,
            (panel.x + int(20 * scale), row_y + int(9 * scale)),
            "small",
            theme.text,
            anchor="midleft",
        )
        played = record.played if record else 0
        won = record.won if record else 0
        lost = record.lost if record else 0
        drawn = record.drawn if record else 0
        bar = Rect(
            panel.x + int(120 * scale),
            row_y + int(3 * scale),
            int(300 * scale),
            int(12 * scale),
        )
        fraction = (won / played) if played else 0.0
        draw_bar(
            surface,
            bar,
            fraction,
            theme,
            theme.good,
            shade(theme.panel, 0.75),
            radius=int(6 * scale),
        )
        draw_text(
            surface,
            fonts,
            f"{won}W {lost}L {drawn}D",
            (bar.right + int(10 * scale), row_y + int(9 * scale)),
            "tiny",
            theme.text_dim,
            anchor="midleft",
        )
        row_y += int(24 * scale)

    achievements_top = row_y + int(10 * scale)
    draw_text(
        surface,
        fonts,
        "ACHIEVEMENTS",
        (panel.x + int(20 * scale), achievements_top),
        "tiny",
        theme.accent_soft,
        bold=True,
    )
    unlocked = sum(1 for _, done in achievement_progress(stats) if done)
    draw_text(
        surface,
        fonts,
        f"{unlocked}/{len(ACHIEVEMENTS)}",
        (panel.right - int(20 * scale), achievements_top),
        "tiny",
        theme.text_dim,
        anchor="topright",
    )
    y = achievements_top + int(20 * scale)
    columns = 2
    column_w = (panel.w - int(56 * scale)) // columns
    for index, achievement in enumerate(ACHIEVEMENTS):
        column, row = divmod(index, (len(ACHIEVEMENTS) + columns - 1) // columns)
        x = panel.x + int(20 * scale) + column * column_w
        y_row = y + row * int(30 * scale)
        done = stats.has_achievement(achievement.key)
        dot_center = (x + int(6 * scale), y_row + int(10 * scale))
        if done:
            pg.draw.circle(surface, theme.good, dot_center, int(5 * scale))
        else:
            pg.draw.circle(surface, theme.panel_border, dot_center, int(5 * scale), 1)
        draw_text(
            surface,
            fonts,
            fit_text(fonts, achievement.title, "tiny", column_w - int(30 * scale)),
            (x + int(18 * scale), y_row + int(3 * scale)),
            "tiny",
            theme.text if done else theme.text_dim,
            bold=done,
        )
        draw_text(
            surface,
            fonts,
            fit_text(
                fonts, achievement.description, "tiny", column_w - int(30 * scale)
            ),
            (x + int(18 * scale), y_row + int(15 * scale)),
            "tiny",
            theme.text_dim if done else shade(theme.text_dim, 0.75),
        )
    return targets


# ---------------------------------------------------------------------------
# Game over
# ---------------------------------------------------------------------------


def draw_game_over(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    data: GameOverData,
) -> List[ClickTarget]:
    scale = layout.ui_scale
    _scrim(surface, layout, alpha=170)
    panel = _panel(layout, 560, 500)
    draw_panel(surface, panel, theme, radius=int(14 * scale))
    targets: List[ClickTarget] = []

    session = data.session
    black, white = session.score()
    if data.reason == "time":
        winner = session.winner
        title = f"{'Black' if winner == PLAYER_BLACK else 'White'} wins on time"
    elif session.winner == 0:
        title = "Draw"
    elif session.winner == PLAYER_BLACK:
        title = "Black wins"
    elif session.winner == PLAYER_WHITE:
        title = "White wins"
    else:
        title = "Game over"
    color = theme.accent if session.winner not in (None, 0) else theme.text

    draw_text(
        surface,
        fonts,
        title,
        (panel.centerx, panel.y + int(28 * scale)),
        "display",
        color,
        anchor="center",
        bold=True,
    )
    draw_text(
        surface,
        fonts,
        f"Black {black}   ·   White {white}",
        (panel.centerx, panel.y + int(70 * scale)),
        "heading",
        theme.text,
        anchor="center",
    )

    detail = (
        f"{session.move_count} moves · {format_clock(session.elapsed())} · "
        f"{MODE_LABELS.get(session.mode, '')} · {session.level_name()}"
    )
    draw_text(
        surface,
        fonts,
        detail,
        (panel.centerx, panel.y + int(96 * scale)),
        "small",
        theme.text_dim,
        anchor="center",
    )

    body_top = panel.y + int(126 * scale)
    body = Rect(
        panel.x + int(24 * scale), body_top, panel.w - int(48 * scale), int(220 * scale)
    )
    pg.draw.rect(surface, shade(theme.panel, 0.94), body.as_tuple(), border_radius=8)

    if data.review is not None:
        _draw_review_summary(surface, fonts, theme, body, data.review, scale)
    else:
        done, total = data.review_progress
        draw_text(
            surface,
            fonts,
            "Analysing the game…" if done < total else "Analysis unavailable",
            (body.x + int(14 * scale), body.y + int(14 * scale)),
            "small",
            theme.text_dim,
        )
        if total:
            bar = Rect(
                body.x + int(14 * scale),
                body.y + int(40 * scale),
                body.w - int(28 * scale),
                int(8 * scale),
            )
            draw_bar(
                surface,
                bar,
                done / max(1, total),
                theme,
                theme.accent,
                shade(theme.panel, 0.8),
            )

    if data.achievements:
        y = body.bottom - int(28 * scale)
        for index, key in enumerate(list(data.achievements)[:3]):
            draw_text(
                surface,
                fonts,
                f"★ {key.replace('_', ' ').title()}",
                (body.x + int(14 * scale) + index * int(150 * scale), y),
                "tiny",
                theme.accent,
            )

    footer = Rect(
        panel.x + int(24 * scale),
        panel.bottom - int(62 * scale),
        panel.w - int(48 * scale),
        int(36 * scale),
    )
    buttons = [
        Button(
            "rematch",
            "Rematch",
            Rect(footer.x, footer.y, int(112 * scale), footer.h),
            "primary",
        ),
        Button(
            "review",
            "Analysis",
            Rect(footer.x + int(120 * scale), footer.y, int(112 * scale), footer.h),
        ),
        Button(
            "stats",
            "Stats",
            Rect(footer.x + int(240 * scale), footer.y, int(96 * scale), footer.h),
        ),
        Button(
            "close",
            "Close",
            Rect(footer.right - int(96 * scale), footer.y, int(96 * scale), footer.h),
        ),
    ]
    for button in buttons:
        button.draw(surface, fonts, theme, radius=int(6 * scale))
        targets.append(ClickTarget(button.rect, "button", button.key))
    return targets


def _draw_review_summary(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    body: Rect,
    review: GameReview,
    scale: float,
) -> None:
    y = body.y + int(12 * scale)
    draw_text(
        surface,
        fonts,
        "ACCURACY",
        (body.x + int(14 * scale), y),
        "tiny",
        theme.accent_soft,
        bold=True,
    )
    y += int(18 * scale)
    for player, label in ((PLAYER_BLACK, "Black"), (PLAYER_WHITE, "White")):
        accuracy = review.accuracy(player)
        draw_text(
            surface,
            fonts,
            label,
            (body.x + int(14 * scale), y),
            "small",
            theme.text,
        )
        bar = Rect(
            body.x + int(74 * scale),
            y + int(4 * scale),
            int(180 * scale),
            int(10 * scale),
        )
        draw_bar(
            surface, bar, accuracy / 100.0, theme, theme.good, shade(theme.panel, 0.8)
        )
        draw_text(
            surface,
            fonts,
            f"{accuracy:.0f}%",
            (bar.right + int(8 * scale), y + int(9 * scale)),
            "tiny",
            theme.text_dim,
            anchor="midleft",
        )
        counts = review.counts(player)
        draw_text(
            surface,
            fonts,
            f"{counts[BLUNDER]} blunders · {counts[MISTAKE]} mistakes · "
            f"{counts[INACCURACY]} inaccuracies",
            (body.x + int(14 * scale), y + int(18 * scale)),
            "tiny",
            theme.text_dim,
        )
        y += int(46 * scale)

    worst = review.worst(limit=3)
    if worst:
        draw_text(
            surface,
            fonts,
            "KEY MOMENTS",
            (body.x + int(14 * scale), y),
            "tiny",
            theme.accent_soft,
            bold=True,
        )
        y += int(16 * scale)
        for item in worst:
            draw_text(
                surface,
                fonts,
                f"{item.ply}. {item.move_name} ({item.label}) → {item.best_move_name}",
                (body.x + int(14 * scale), y),
                "tiny",
                theme.text_dim,
            )
            y += int(15 * scale)


# ---------------------------------------------------------------------------
# Resume prompt
# ---------------------------------------------------------------------------


def draw_resume(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    data: ResumeData,
) -> List[ClickTarget]:
    scale = layout.ui_scale
    _scrim(surface, layout)
    panel = _panel(layout, 460, 240)
    draw_panel(surface, panel, theme, radius=int(14 * scale))
    draw_text(
        surface,
        fonts,
        "Resume saved game?",
        (panel.centerx, panel.y + int(30 * scale)),
        "heading",
        theme.text,
        anchor="center",
        bold=True,
    )
    lines = [
        f"{data.move_count} moves played",
        f"{data.mode}" + (f" · {data.level}" if data.level else ""),
    ]
    if data.played_at:
        lines.append(f"Saved {data.played_at}")
    y = panel.y + int(66 * scale)
    for line in lines:
        draw_text(
            surface,
            fonts,
            line,
            (panel.centerx, y),
            "small",
            theme.text_dim,
            anchor="center",
        )
        y += int(22 * scale)

    targets: List[ClickTarget] = []
    footer = Rect(
        panel.x + int(24 * scale),
        panel.bottom - int(58 * scale),
        panel.w - int(48 * scale),
        int(36 * scale),
    )
    buttons = [
        Button(
            "resume",
            "Resume",
            Rect(footer.x, footer.y, int(140 * scale), footer.h),
            "primary",
        ),
        Button(
            "discard",
            "Start fresh",
            Rect(footer.right - int(140 * scale), footer.y, int(140 * scale), footer.h),
        ),
    ]
    for button in buttons:
        button.draw(surface, fonts, theme, radius=int(6 * scale))
        targets.append(ClickTarget(button.rect, "button", button.key))
    return targets


__all__ = [
    "ClickTarget",
    "GameOverData",
    "OPTION_TABS",
    "OptionsData",
    "ResumeData",
    "draw_game_over",
    "draw_help",
    "draw_options",
    "draw_resume",
    "draw_stats",
]
