"""Reusable widgets.

Widgets are stateless value objects: they draw themselves and expose their
rectangle so the controller can hit-test events.  Hover/press state is passed in
by the renderer, which keeps input handling in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import pygame as pg

from .assets import FontBook, mix, shade
from .drawing import draw_ring, draw_text, fit_text
from .layout import Rect
from .theme import Color, Theme

BUTTON_KINDS = ("primary", "secondary", "danger", "ghost")


@dataclass
class Button:
    """A labelled button."""

    key: str
    label: str
    rect: Rect
    kind: str = "secondary"
    enabled: bool = True
    active: bool = False
    tooltip: str = ""
    role: str = "small"

    def colors(self, theme: Theme) -> Tuple[Color, Color, Color]:
        """Return ``(fill, border, text)`` for the current style."""

        if not self.enabled:
            return shade(theme.panel, 0.9), theme.panel_border, theme.text_dim
        if self.active:
            return theme.accent, theme.accent, theme.text_inverse
        if self.kind == "primary":
            return theme.accent, theme.accent, theme.text_inverse
        if self.kind == "danger":
            return shade(theme.bad, 0.85), theme.bad, theme.text
        if self.kind == "ghost":
            return theme.panel, theme.panel_border, theme.text_dim
        return theme.panel_raised, theme.panel_border, theme.text

    def draw(
        self,
        surface: pg.Surface,
        fonts: FontBook,
        theme: Theme,
        hovered: bool = False,
        pressed: bool = False,
        focused: bool = False,
        radius: int = 7,
    ) -> None:
        fill, border, text_color = self.colors(theme)
        if hovered and self.enabled:
            fill = mix(fill, (255, 255, 255), 0.10)
        if pressed and self.enabled:
            fill = mix(fill, (0, 0, 0), 0.12)
        rect = self.rect.moved(0, 1) if pressed else self.rect

        pg.draw.rect(surface, fill, rect.as_tuple(), border_radius=radius)
        pg.draw.rect(
            surface,
            border if self.enabled else theme.panel_border,
            rect.as_tuple(),
            1,
            border_radius=radius,
        )
        if self.active or (focused and self.enabled):
            draw_ring(surface, rect.center, max(4, rect.h // 2), theme.accent, 1)

        label = fit_text(fonts, self.label, self.role, rect.w - 12)
        draw_text(
            surface,
            fonts,
            label,
            rect.center,
            role=self.role,
            color=text_color,
            anchor="center",
            bold=self.kind == "primary" or self.active,
        )


def focus_ring(surface: pg.Surface, rect: Rect, theme: Theme, radius: int = 8) -> None:
    pg.draw.rect(
        surface, theme.accent, rect.inset(-2).as_tuple(), 2, border_radius=radius + 2
    )


def draw_segmented(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    options: Sequence[str],
    active: int,
    *,
    enabled: bool = True,
    scale: float = 1.0,
    gap: int = 4,
    radius: int = 6,
) -> List[Rect]:
    """Draw a row of mutually exclusive options; return their rectangles."""

    if not options:
        return []
    count = len(options)
    gap = int(gap * scale)
    width = (rect.w - gap * (count - 1)) // count
    rects: List[Rect] = []
    for index, option in enumerate(options):
        item = Rect(rect.x + index * (width + gap), rect.y, width, rect.h)
        selected = index == active
        if not enabled:
            fill, text_color = shade(theme.panel, 0.92), theme.text_dim
        elif selected:
            fill, text_color = theme.accent, theme.text_inverse
        else:
            fill, text_color = theme.panel_raised, theme.text_dim
        pg.draw.rect(surface, fill, item.as_tuple(), border_radius=radius)
        pg.draw.rect(
            surface,
            theme.panel_border if not selected else theme.accent,
            item.as_tuple(),
            1,
            border_radius=radius,
        )
        label = fit_text(fonts, option, "small", item.w - 10)
        draw_text(
            surface,
            fonts,
            label,
            item.center,
            role="small",
            color=text_color,
            anchor="center",
            bold=selected,
        )
        rects.append(item)
    return rects


def draw_toggle(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    label: str,
    value: bool,
    *,
    enabled: bool = True,
) -> Rect:
    """Draw a label plus an iOS-style switch; return the switch rectangle."""

    draw_text(
        surface,
        fonts,
        label,
        (rect.x, rect.centery),
        role="body",
        color=theme.text if enabled else theme.text_dim,
        anchor="midleft",
    )
    track_w = int(44 * max(1.0, rect.h / 28))
    track_h = int(22 * max(1.0, rect.h / 28))
    track = Rect(rect.right - track_w, rect.centery - track_h // 2, track_w, track_h)
    track_color = theme.accent if value else shade(theme.panel, 0.75)
    pg.draw.rect(surface, track_color, track.as_tuple(), border_radius=track_h // 2)
    pg.draw.rect(
        surface, theme.panel_border, track.as_tuple(), 1, border_radius=track_h // 2
    )
    knob_radius = track_h // 2 - 3
    knob_x = track.right - knob_radius - 4 if value else track.x + knob_radius + 4
    pg.draw.circle(
        surface,
        theme.text if value else theme.text_dim,
        (knob_x, track.centery),
        knob_radius,
    )
    return track


def draw_slider(
    surface: pg.Surface,
    theme: Theme,
    rect: Rect,
    value: float,
    *,
    enabled: bool = True,
) -> Rect:
    """Draw a horizontal slider; return the knob rectangle."""

    value = max(0.0, min(1.0, value))
    track = Rect(rect.x, rect.centery - 3, rect.w, 6)
    pg.draw.rect(surface, shade(theme.panel, 0.75), track.as_tuple(), border_radius=3)
    filled_w = int(track.w * value)
    if filled_w > 0:
        pg.draw.rect(
            surface,
            theme.accent if enabled else theme.text_dim,
            (track.x, track.y, filled_w, track.h),
            border_radius=3,
        )
    knob_x = track.x + filled_w
    knob_radius = max(6, rect.h // 2 - 4)
    pg.draw.circle(
        surface,
        theme.text if enabled else theme.text_dim,
        (knob_x, track.centery),
        knob_radius,
    )
    pg.draw.circle(surface, theme.accent, (knob_x, track.centery), knob_radius, 2)
    return Rect(
        knob_x - knob_radius,
        track.centery - knob_radius,
        knob_radius * 2,
        knob_radius * 2,
    )


def draw_tabs(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    labels: Sequence[str],
    active: int,
) -> List[Rect]:
    """Draw a horizontal tab strip; return tab rectangles."""

    rects: List[Rect] = []
    x = rect.x
    for index, label in enumerate(labels):
        text_surface = fonts.render(
            label,
            "small",
            theme.text if index == active else theme.text_dim,
            bold=index == active,
        )
        width = text_surface.get_width() + 24
        item = Rect(x, rect.y, width, rect.h)
        if index == active:
            pg.draw.rect(surface, theme.panel_raised, item.as_tuple(), border_radius=6)
            pg.draw.line(
                surface,
                theme.accent,
                (item.x + 8, item.bottom - 3),
                (item.right - 8, item.bottom - 3),
                2,
            )
        surface.blit(
            text_surface,
            (
                item.centerx - text_surface.get_width() // 2,
                item.centery - text_surface.get_height() // 2,
            ),
        )
        rects.append(item)
        x += width
    return rects


def draw_badge(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    position: Tuple[int, int],
    text: str,
    color: Color,
    anchor: str = "topleft",
) -> Rect:
    """Draw a small pill-shaped badge and return its rectangle."""

    text_surface = fonts.render(text, "tiny", theme.text_inverse, bold=True)
    width = text_surface.get_width() + 14
    height = text_surface.get_height() + 6
    if anchor == "center":
        rect = Rect(position[0] - width // 2, position[1] - height // 2, width, height)
    elif anchor == "topright":
        rect = Rect(position[0] - width, position[1], width, height)
    elif anchor == "midright":
        rect = Rect(position[0] - width, position[1] - height // 2, width, height)
    else:
        rect = Rect(position[0], position[1], width, height)
    pg.draw.rect(surface, color, rect.as_tuple(), border_radius=height // 2)
    surface.blit(
        text_surface,
        (
            rect.centerx - text_surface.get_width() // 2,
            rect.centery - text_surface.get_height() // 2,
        ),
    )
    return rect


def draw_tooltip(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    text: str,
    position: Tuple[int, int],
    bounds: Rect,
) -> None:
    """Draw a tooltip near *position*, clamped inside *bounds*."""

    if not text:
        return
    text_surface = fonts.render(text, "tiny", theme.text)
    width = text_surface.get_width() + 16
    height = text_surface.get_height() + 10
    x = min(max(bounds.x, position[0] + 14), bounds.right - width)
    y = min(max(bounds.y, position[1] + 18), bounds.bottom - height)
    rect = Rect(x, y, width, height)
    pg.draw.rect(surface, theme.background_deep, rect.as_tuple(), border_radius=5)
    pg.draw.rect(surface, theme.panel_border, rect.as_tuple(), 1, border_radius=5)
    surface.blit(text_surface, (x + 8, y + 5))


def draw_keycap(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    position: Tuple[int, int],
    label: str,
) -> int:
    """Draw a keyboard key cap and return its width."""

    text_surface = fonts.render(label, "tiny", theme.text)
    width = text_surface.get_width() + 10
    height = text_surface.get_height() + 6
    rect = Rect(position[0], position[1] - height // 2, width, height)
    pg.draw.rect(surface, theme.panel_raised, rect.as_tuple(), border_radius=4)
    pg.draw.rect(surface, theme.panel_border, rect.as_tuple(), 1, border_radius=4)
    surface.blit(
        text_surface,
        (
            rect.centerx - text_surface.get_width() // 2,
            rect.centery - text_surface.get_height() // 2,
        ),
    )
    return width


def draw_scrollbar(
    surface: pg.Surface,
    theme: Theme,
    track: Rect,
    offset: int,
    content_height: int,
    view_height: int,
) -> None:
    """Draw a minimal scrollbar when the content overflows."""

    if content_height <= view_height:
        return
    ratio = view_height / content_height
    height = max(24, int(track.h * ratio))
    max_offset = max(1, content_height - view_height)
    position = max(0.0, min(1.0, offset / max_offset))
    y = track.y + int((track.h - height) * position)
    pg.draw.rect(surface, shade(theme.panel, 0.8), track.as_tuple(), border_radius=3)
    pg.draw.rect(
        surface,
        theme.text_dim,
        (track.x + 2, y, max(2, track.w - 4), height),
        border_radius=3,
    )


__all__ = [
    "BUTTON_KINDS",
    "Button",
    "draw_badge",
    "draw_keycap",
    "draw_scrollbar",
    "draw_segmented",
    "draw_slider",
    "draw_tabs",
    "draw_toggle",
    "draw_tooltip",
    "focus_ring",
]
