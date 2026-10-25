"""Menu bar and status panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import pygame as pg

from ..app.session import Session
from ..core.constants import PLAYER_BLACK
from .assets import FontBook, mix, shade
from .drawing import draw_bar, draw_ring, draw_text, fit_text
from .layout import Layout, Rect
from .theme import Color, Theme
from .widgets import Button, draw_tooltip


def format_clock(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_menubar(layout: Layout, session: Session) -> List[Button]:
    """Create the menu-bar buttons for the current layout."""

    scale = layout.ui_scale
    height = int(26 * scale)
    gap = int(6 * scale)
    x = int(16 * scale)
    y = layout.menubar.centery - height // 2
    buttons: List[Button] = []
    for key, label, width in (
        ("new_game", "New Game", 96),
        ("undo", "Undo", 68),
        ("redo", "Redo", 68),
        ("hint", "Hint", 62),
        ("options", "Options", 82),
        ("help", "Help", 62),
    ):
        button = Button(key, label, Rect(x, y, int(width * scale), height))
        if key == "undo":
            button.enabled = session.can_undo()
        elif key == "redo":
            button.enabled = session.can_redo()
        buttons.append(button)
        x += int(width * scale) + gap
    return buttons


def draw_menubar(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    buttons: Sequence[Button],
    title: str,
    hovered: Optional[str] = None,
    pressed: Optional[str] = None,
    badge: Optional[str] = None,
    message: str = "",
) -> None:
    rect = layout.menubar
    surface.blit(_menubar_gradient(theme, rect), (rect.x, rect.y))
    pg.draw.line(
        surface,
        shade(theme.panel_border, 0.8),
        (rect.x, rect.bottom - 1),
        (rect.right, rect.bottom - 1),
    )

    for button in buttons:
        button.draw(
            surface,
            fonts,
            theme,
            hovered=hovered == button.key,
            pressed=pressed == button.key,
            radius=int(6 * layout.ui_scale),
        )

    title_surface = fonts.render(title, "title", theme.accent, bold=True)
    title_x = rect.right - title_surface.get_width() - int(18 * layout.ui_scale)
    surface.blit(
        title_surface, (title_x, rect.centery - title_surface.get_height() // 2)
    )

    if badge:
        badge_surface = fonts.render(badge, "tiny", theme.text_dim)
        surface.blit(
            badge_surface,
            (
                title_x - badge_surface.get_width() - int(10 * layout.ui_scale),
                rect.centery - badge_surface.get_height() // 2,
            ),
        )
    if message:
        message_surface = fonts.render(message, "tiny", theme.text_dim)
        surface.blit(
            message_surface,
            (
                title_x - message_surface.get_width() - int(10 * layout.ui_scale),
                rect.centery
                - message_surface.get_height() // 2
                - int(8 * layout.ui_scale),
            ),
        )


_GRADIENT_CACHE: dict = {}


def _menubar_gradient(theme: Theme, rect: Rect) -> pg.Surface:
    key = (theme.key, rect.w, rect.h)
    cached = _GRADIENT_CACHE.get(key)
    if cached is None:
        surface = pg.Surface((rect.w, rect.h)).convert()
        top = mix(theme.background, (255, 255, 255), 0.05)
        bottom = shade(theme.background, 0.85)
        for index in range(rect.h):
            color = mix(top, bottom, index / max(1, rect.h - 1))
            pg.draw.line(surface, color, (0, index), (rect.w, index))
        _GRADIENT_CACHE[key] = surface
    return _GRADIENT_CACHE[key]


@dataclass
class StatusData:
    """Everything the status panel needs, already formatted."""

    black_score: int = 2
    white_score: int = 2
    shown_black: int = 2
    shown_white: int = 2
    turn_name: str = "Black"
    turn_player: Optional[int] = PLAYER_BLACK
    banner: str = "Black to move"
    banner_color: Optional[Color] = None
    mode_line: str = ""
    opening: Optional[str] = None
    probability: float = 0.5
    thinking_text: str = ""
    thinking_detail: str = ""
    message: str = ""
    message_color: Optional[Color] = None
    clock_black: str = ""
    clock_white: str = ""
    clock_urgent: bool = False
    show_eval_bar: bool = True
    human_turn: bool = True
    result: bool = False


def draw_status(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    data: StatusData,
) -> None:
    """Render the bottom panel: score, mode, turn, clocks and evaluation."""

    rect = layout.status
    scale = layout.ui_scale
    padding = int(18 * scale)

    surface.blit(_status_gradient(theme, rect), (rect.x, rect.y))
    pg.draw.line(
        surface,
        shade(theme.panel_border, 0.85),
        (rect.x, rect.y),
        (rect.right, rect.y),
    )

    narrow = rect.w < int(1000 * scale)
    left_w = int(238 * scale) if narrow else int(290 * scale)
    right_w = 0 if narrow else int(260 * scale)
    left = Rect(rect.x + padding, rect.y + int(10 * scale), left_w, rect.h)

    if right_w:
        right = Rect(rect.right - padding - right_w, left.y, right_w, rect.h)
        middle = Rect(
            left.right + int(16 * scale),
            left.y,
            max(120, right.x - left.right - int(32 * scale)),
            rect.h,
        )
    else:
        right = None
        middle = Rect(
            left.right + int(16 * scale),
            left.y,
            max(120, rect.right - padding - left.right - int(16 * scale)),
            rect.h - int(8 * scale),
        )

    _draw_score_block(surface, fonts, theme, left, data, scale)
    _draw_turn_block(surface, fonts, theme, middle, data, scale)

    if data.show_eval_bar and right is None:
        _draw_compact_eval(surface, fonts, theme, middle, data)

    if data.show_eval_bar and right is not None:
        bar = Rect(right.x, right.y + int(6 * scale), right.w, int(10 * scale))
        draw_bar(
            surface,
            bar,
            data.probability,
            theme,
            theme.eval_black,
            theme.eval_white,
            radius=int(5 * scale),
        )
        percent = int(round(data.probability * 100))
        draw_text(
            surface,
            fonts,
            f"Black {percent}%",
            (bar.x, bar.y - int(4 * scale)),
            "tiny",
            theme.text_dim,
            anchor="bottomleft",
        )
        draw_text(
            surface,
            fonts,
            f"White {100 - percent}%",
            (bar.right, bar.y - int(4 * scale)),
            "tiny",
            theme.text_dim,
            anchor="bottomright",
        )
        if data.thinking_text:
            draw_text(
                surface,
                fonts,
                fit_text(fonts, data.thinking_text, "tiny", right.w),
                (right.x, bar.bottom + int(8 * scale)),
                "tiny",
                theme.accent,
            )
        if data.thinking_detail:
            draw_text(
                surface,
                fonts,
                fit_text(fonts, data.thinking_detail, "tiny", right.w),
                (right.x, bar.bottom + int(26 * scale)),
                "tiny",
                theme.text_dim,
            )
        if data.clock_black or data.clock_white:
            clock_color = theme.warn if data.clock_urgent else theme.text_dim
            draw_text(
                surface,
                fonts,
                f"{data.clock_black}  ·  {data.clock_white}",
                (right.x, bar.bottom + int(44 * scale)),
                "small",
                clock_color,
            )


def _draw_compact_eval(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    data: StatusData,
) -> None:
    """Slim evaluation bar and thinking readout for narrow windows."""

    bar = Rect(rect.x, rect.bottom - 12, rect.w, 6)
    draw_bar(
        surface,
        bar,
        data.probability,
        theme,
        theme.eval_black,
        theme.eval_white,
        radius=3,
    )
    percent = int(round(data.probability * 100))
    draw_text(
        surface,
        fonts,
        f"B {percent}%",
        (bar.x, bar.y - 2),
        "tiny",
        theme.text_dim,
        anchor="bottomleft",
    )
    draw_text(
        surface,
        fonts,
        f"W {100 - percent}%",
        (bar.right, bar.y - 2),
        "tiny",
        theme.text_dim,
        anchor="bottomright",
    )
    if data.thinking_text and not data.message:
        draw_text(
            surface,
            fonts,
            fit_text(fonts, data.thinking_text, "tiny", rect.w),
            (rect.x, rect.centery + 18),
            "tiny",
            theme.accent,
        )


def _draw_score_block(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    data: StatusData,
    scale: float,
) -> None:
    disc_radius = int(10 * scale)
    black_center = (rect.x + disc_radius, rect.y + int(14 * scale))
    pg.draw.circle(surface, theme.black_body, black_center, disc_radius)
    pg.draw.circle(surface, theme.black_rim, black_center, disc_radius, 2)
    draw_text(
        surface,
        fonts,
        f"{data.shown_black}",
        (black_center[0] + disc_radius + int(8 * scale), black_center[1]),
        "title",
        theme.text,
        anchor="midleft",
        bold=True,
    )

    white_center = (rect.x + int(118 * scale), rect.y + int(14 * scale))
    pg.draw.circle(surface, theme.white_body, white_center, disc_radius)
    pg.draw.circle(surface, theme.white_rim, white_center, disc_radius, 2)
    draw_text(
        surface,
        fonts,
        f"{data.shown_white}",
        (white_center[0] + disc_radius + int(8 * scale), white_center[1]),
        "title",
        theme.text,
        anchor="midleft",
        bold=True,
    )

    draw_text(
        surface,
        fonts,
        fit_text(fonts, data.mode_line, "small", rect.w),
        (rect.x, rect.y + int(46 * scale)),
        "small",
        theme.text_dim,
    )
    if data.opening:
        draw_text(
            surface,
            fonts,
            fit_text(fonts, data.opening, "small", rect.w),
            (rect.x, rect.y + int(68 * scale)),
            "small",
            theme.accent_soft,
        )


def _draw_turn_block(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    data: StatusData,
    scale: float,
) -> None:
    color = data.banner_color or theme.text
    if data.turn_player is not None:
        center = (rect.x + int(10 * scale), rect.centery - int(10 * scale))
        radius = int(9 * scale)
        if data.turn_player == PLAYER_BLACK:
            pg.draw.circle(surface, theme.black_body, center, radius)
            pg.draw.circle(surface, theme.black_rim, center, radius, 2)
        else:
            pg.draw.circle(surface, theme.white_body, center, radius)
            pg.draw.circle(surface, theme.white_rim, center, radius, 2)
        if data.human_turn:
            draw_ring(surface, center, radius + int(4 * scale), theme.accent, 1)
        text_x = center[0] + radius + int(10 * scale)
    else:
        text_x = rect.x

    draw_text(
        surface,
        fonts,
        fit_text(fonts, data.banner, "title", rect.w - (text_x - rect.x), bold=True),
        (text_x, rect.centery - int(14 * scale)),
        "title",
        color,
        anchor="midleft",
        bold=True,
    )

    if data.message:
        draw_text(
            surface,
            fonts,
            fit_text(fonts, data.message, "small", rect.w),
            (rect.x, rect.centery + int(18 * scale)),
            "small",
            data.message_color or theme.text_dim,
        )


_STATUS_CACHE: dict = {}


def _status_gradient(theme: Theme, rect: Rect) -> pg.Surface:
    key = (theme.key, rect.w, rect.h, "status")
    cached = _STATUS_CACHE.get(key)
    if cached is None:
        surface = pg.Surface((rect.w, rect.h)).convert()
        top = mix(theme.background, theme.panel, 0.55)
        bottom = theme.background_deep
        for index in range(rect.h):
            color = mix(top, bottom, index / max(1, rect.h - 1))
            pg.draw.line(surface, color, (0, index), (rect.w, index))
        _STATUS_CACHE[key] = surface
    return _STATUS_CACHE[key]


def draw_tooltip_for_buttons(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    buttons: Sequence[Button],
    mouse: Optional[Tuple[int, int]],
) -> None:
    if mouse is None:
        return
    for button in buttons:
        if button.tooltip and button.rect.contains(mouse):
            draw_tooltip(
                surface,
                fonts,
                theme,
                button.tooltip,
                mouse,
                Rect(0, 0, layout.width, layout.height),
            )
            return


__all__ = [
    "StatusData",
    "build_menubar",
    "draw_menubar",
    "draw_status",
    "draw_tooltip_for_buttons",
    "format_clock",
]
