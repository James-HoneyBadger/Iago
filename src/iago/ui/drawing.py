"""Low-level drawing helpers.

Small, composable functions with caching where it matters (gradients).  Every
function takes explicit colours so the caller decides which theme is in use.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

import pygame as pg

from .assets import FontBook, mix, shade
from .layout import Rect
from .theme import Color, Theme

_GRADIENTS: Dict[Tuple[int, int, Color, Color, bool], pg.Surface] = {}


def with_alpha(color: Color, alpha: int) -> Tuple[int, int, int, int]:
    return color[0], color[1], color[2], max(0, min(255, alpha))


def gradient(
    size: Tuple[int, int],
    top: Color,
    bottom: Color,
    horizontal: bool = False,
) -> pg.Surface:
    """Return a cached linear gradient surface."""

    key = (size[0], size[1], top, bottom, horizontal)
    cached = _GRADIENTS.get(key)
    if cached is not None:
        return cached

    width, height = max(1, size[0]), max(1, size[1])
    surface = pg.Surface((width, height))
    if pg.display.get_init() and pg.display.get_surface() is not None:
        surface = surface.convert()
    length = width if horizontal else height
    for index in range(length):
        t = index / max(1, length - 1)
        color = mix(top, bottom, t)
        if horizontal:
            pg.draw.line(surface, color, (index, 0), (index, height))
        else:
            pg.draw.line(surface, color, (0, index), (width, index))
    _GRADIENTS[key] = surface
    return surface


def clear_gradient_cache() -> None:
    _GRADIENTS.clear()


def draw_shadow(
    surface: pg.Surface,
    rect: Rect,
    radius: int = 14,
    spread: int = 8,
    alpha: int = 90,
) -> None:
    """Draw a soft drop shadow behind *rect*."""

    for step in range(spread, 0, -1):
        layer_alpha = int(alpha * (1.0 - step / (spread + 1)) ** 2)
        if layer_alpha <= 0:
            continue
        layer = pg.Surface((rect.w + step * 2, rect.h + step * 2), pg.SRCALPHA)
        pg.draw.rect(
            layer,
            (0, 0, 0, layer_alpha),
            (0, 0, layer.get_width(), layer.get_height()),
            border_radius=radius + step,
        )
        surface.blit(layer, (rect.x - step, rect.y - step + 3))


def draw_panel(
    surface: pg.Surface,
    rect: Rect,
    theme: Theme,
    radius: int = 14,
    raised: bool = True,
    shadow: bool = True,
    border: bool = True,
) -> None:
    """Draw a filled, optionally elevated panel with a 1px border."""

    if shadow:
        draw_shadow(surface, rect, radius=radius, spread=10, alpha=80)

    fill = theme.panel_raised if raised else theme.panel
    pg.draw.rect(surface, fill, rect.as_tuple(), border_radius=radius)
    top = mix(fill, (255, 255, 255), 0.06)
    bottom = mix(fill, (0, 0, 0), 0.10)
    band = pg.Surface((rect.w, max(2, rect.h // 2)), pg.SRCALPHA)
    for index in range(band.get_height()):
        t = index / max(1, band.get_height() - 1)
        color = mix(top, bottom, t)
        pg.draw.line(band, (*color, 40), (0, index), (rect.w, index))
    mask = pg.Surface((rect.w, rect.h), pg.SRCALPHA)
    pg.draw.rect(
        mask, (255, 255, 255, 255), (0, 0, rect.w, rect.h), border_radius=radius
    )
    band_surface = pg.Surface((rect.w, rect.h), pg.SRCALPHA)
    band_surface.blit(band, (0, 0))
    band_surface.blit(mask, (0, 0), special_flags=pg.BLEND_RGBA_MULT)
    surface.blit(band_surface, (rect.x, rect.y))

    if border:
        pg.draw.rect(
            surface, theme.panel_border, rect.as_tuple(), 1, border_radius=radius
        )


def draw_separator(
    surface: pg.Surface, start: Tuple[int, int], end: Tuple[int, int], theme: Theme
) -> None:
    pg.draw.line(surface, shade(theme.panel_border, 0.9), start, end, 1)


def draw_text(
    surface: pg.Surface,
    fonts: FontBook,
    text: str,
    position: Tuple[int, int],
    role: str = "body",
    color: Color = (255, 255, 255),
    anchor: str = "topleft",
    bold: bool = False,
) -> Rect:
    """Blit cached text and return its rectangle."""

    rendered = fonts.render(text, role, color, bold)
    rect = rendered.get_rect()
    setattr(rect, anchor, position)
    surface.blit(rendered, rect)
    return Rect(rect.x, rect.y, rect.w, rect.h)


def draw_label_value(
    surface: pg.Surface,
    fonts: FontBook,
    label: str,
    value: str,
    position: Tuple[int, int],
    theme: Theme,
    role: str = "small",
    value_color: Optional[Color] = None,
) -> int:
    """Draw ``label: value`` inline and return the consumed width."""

    label_surface = fonts.render(label, role, theme.text_dim)
    value_surface = fonts.render(value, role, value_color or theme.text, bold=True)
    surface.blit(label_surface, position)
    surface.blit(
        value_surface,
        (position[0] + label_surface.get_width() + 6, position[1]),
    )
    return label_surface.get_width() + 6 + value_surface.get_width()


def draw_bar(
    surface: pg.Surface,
    rect: Rect,
    fraction: float,
    theme: Theme,
    left_color: Color,
    right_color: Color,
    track_color: Optional[Color] = None,
    radius: int = 5,
) -> None:
    """Draw a two-colour progress bar."""

    fraction = max(0.0, min(1.0, fraction))
    pg.draw.rect(
        surface,
        track_color or shade(theme.panel, 0.8),
        rect.as_tuple(),
        border_radius=radius,
    )
    split = int(rect.w * fraction)
    if split > 0:
        pg.draw.rect(
            surface,
            left_color,
            (rect.x, rect.y, split, rect.h),
            border_radius=radius,
        )
    if split < rect.w:
        pg.draw.rect(
            surface,
            right_color,
            (rect.x + split, rect.y, rect.w - split, rect.h),
            border_radius=radius,
        )
    pg.draw.rect(
        surface,
        shade(theme.panel_border, 0.9),
        rect.as_tuple(),
        1,
        border_radius=radius,
    )


def draw_glow(
    surface: pg.Surface,
    center: Tuple[int, int],
    radius: int,
    color: Color,
    alpha: int = 90,
    layers: int = 4,
) -> None:
    """Draw a soft circular glow."""

    glow = pg.Surface((radius * 2, radius * 2), pg.SRCALPHA)
    for step in range(layers, 0, -1):
        layer_alpha = int(alpha * (step / layers) ** 2)
        pg.draw.circle(
            glow, (*color, layer_alpha), (radius, radius), radius * step // layers
        )
    surface.blit(glow, (center[0] - radius, center[1] - radius))


def draw_star(
    surface: pg.Surface, center: Tuple[int, int], radius: int, color: Color
) -> None:
    """Draw a five-pointed star."""

    points = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        r = radius if index % 2 == 0 else radius * 0.44
        points.append(
            (center[0] + int(r * math.cos(angle)), center[1] + int(r * math.sin(angle)))
        )
    pg.draw.polygon(surface, color, points)


def draw_diamond(
    surface: pg.Surface, center: Tuple[int, int], radius: int, color: Color
) -> None:
    x, y = center
    pg.draw.polygon(
        surface,
        color,
        [(x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)],
    )


def draw_ring(
    surface: pg.Surface,
    center: Tuple[int, int],
    radius: int,
    color: Color,
    width: int = 2,
) -> None:
    pg.draw.circle(surface, color, center, radius, width)


def draw_checker(
    surface: pg.Surface,
    rect: Rect,
    cell: int,
    light: Color,
    dark: Color,
    size: int,
) -> None:
    """Fill a board area with a subtle checker pattern."""

    for row in range(size):
        for col in range(size):
            color = light if (row + col) % 2 == 0 else dark
            pg.draw.rect(
                surface,
                color,
                (rect.x + col * cell, rect.y + row * cell, cell, cell),
            )


def draw_bevel(
    surface: pg.Surface,
    rect: Rect,
    theme: Theme,
    radius: int = 10,
    width: int = 2,
) -> None:
    """Draw a raised bevel: light top-left edge, dark bottom-right edge."""

    highlight = mix(theme.frame, (255, 255, 255), 0.28)
    shadow = shade(theme.frame_edge, 0.7)
    pg.draw.line(
        surface,
        highlight,
        (rect.x + radius, rect.y + width // 2),
        (rect.right - radius, rect.y + width // 2),
        width,
    )
    pg.draw.line(
        surface,
        highlight,
        (rect.x + width // 2, rect.y + radius),
        (rect.x + width // 2, rect.bottom - radius),
        width,
    )
    pg.draw.line(
        surface,
        shadow,
        (rect.x + radius, rect.bottom - width),
        (rect.right - radius, rect.bottom - width),
        width,
    )
    pg.draw.line(
        surface,
        shadow,
        (rect.right - width, rect.y + radius),
        (rect.right - width, rect.bottom - radius),
        width,
    )


def fit_text(
    fonts: FontBook,
    text: str,
    role: str,
    max_width: int,
    bold: bool = False,
) -> str:
    """Truncate *text* with an ellipsis so it fits *max_width*."""

    if fonts.measure(text, role, bold)[0] <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and fonts.measure(trimmed + ellipsis, role, bold)[0] > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis if trimmed else ellipsis


def wrap_text(
    fonts: FontBook, text: str, role: str, max_width: int, bold: bool = False
) -> Sequence[str]:
    """Wrap text on spaces to *max_width*."""

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if fonts.measure(candidate, role, bold)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


__all__ = [
    "clear_gradient_cache",
    "draw_bar",
    "draw_bevel",
    "draw_checker",
    "draw_diamond",
    "draw_glow",
    "draw_label_value",
    "draw_panel",
    "draw_ring",
    "draw_separator",
    "draw_shadow",
    "draw_star",
    "draw_text",
    "fit_text",
    "gradient",
    "with_alpha",
    "wrap_text",
]
