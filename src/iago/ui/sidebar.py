"""Move list, opening name and evaluation graph sidebar."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import pygame as pg

from ..app.analysis import BEST, BLUNDER, GOOD, INACCURACY, MISTAKE, GameReview
from ..app.session import MoveRecord
from ..core.constants import PLAYER_BLACK, PLAYER_WHITE
from .assets import FontBook, mix, shade
from .drawing import draw_text, fit_text
from .layout import Layout, Rect
from .theme import Theme
from .widgets import draw_scrollbar

LABEL_COLORS = {
    BEST: (110, 210, 140),
    GOOD: (150, 180, 200),
    INACCURACY: (232, 200, 110),
    MISTAKE: (232, 152, 96),
    BLUNDER: (230, 96, 96),
}


@dataclass
class SidebarData:
    records: Sequence[MoveRecord] = field(default_factory=tuple)
    opening: Optional[str] = None
    selected_ply: Optional[int] = None
    review: Optional[GameReview] = None
    scroll: int = 0
    footer: str = ""
    hint: str = ""
    show_hint: bool = False


@dataclass
class SidebarHit:
    rows: List[Tuple[Rect, int]] = field(default_factory=list)
    content_height: int = 0
    view_height: int = 0
    graph: Optional[Rect] = None


def draw_sidebar(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    layout: Layout,
    data: SidebarData,
) -> Optional[SidebarHit]:
    """Draw the sidebar; returns hit-testing information."""

    rect = layout.sidebar
    if rect is None:
        return None

    scale = layout.ui_scale
    hit = SidebarHit()
    pg.draw.rect(surface, theme.panel, rect.as_tuple())
    pg.draw.line(
        surface,
        shade(theme.panel_border, 0.85),
        (rect.x, rect.y),
        (rect.x, rect.bottom),
    )

    padding = int(12 * scale)
    header_y = rect.y + int(10 * scale)
    draw_text(
        surface,
        fonts,
        "MOVES",
        (rect.x + padding, header_y),
        "tiny",
        theme.text_dim,
        bold=True,
    )
    if data.opening:
        label = fit_text(fonts, data.opening, "tiny", rect.w - int(80 * scale))
        draw_text(
            surface,
            fonts,
            label,
            (rect.right - padding, header_y),
            "tiny",
            theme.accent_soft,
            anchor="topright",
        )

    graph_height = int(58 * scale)
    graph = Rect(
        rect.x + padding,
        header_y + int(20 * scale),
        rect.w - 2 * padding,
        graph_height,
    )
    hit.graph = graph
    _draw_graph(surface, fonts, theme, graph, data, scale)

    list_top = graph.bottom + int(10 * scale)
    footer_height = (
        int(46 * scale) if (data.footer or data.show_hint) else int(8 * scale)
    )
    list_rect = Rect(
        rect.x + int(6 * scale),
        list_top,
        rect.w - int(12 * scale),
        rect.bottom - list_top - footer_height - int(6 * scale),
    )
    hit.view_height = list_rect.h

    row_height = int(24 * scale)
    pairs = (len(data.records) + 1) // 2
    content_height = max(1, pairs) * row_height
    hit.content_height = content_height

    scroll = max(0, min(data.scroll, max(0, content_height - list_rect.h)))
    surface.set_clip(list_rect)
    for pair in range(pairs):
        y = list_top + pair * row_height - scroll
        row = Rect(list_rect.x, y, list_rect.w - int(8 * scale), row_height)
        if row.bottom < list_rect.y or row.y > list_rect.bottom:
            continue
        black_ply = pair * 2 + 1
        white_ply = pair * 2 + 2
        if pair % 2 == 0:
            pg.draw.rect(
                surface,
                mix(theme.panel, theme.panel_raised, 0.5),
                (row.x, row.y, row.w, row.h),
            )
        _draw_row(surface, fonts, theme, row, data, black_ply, PLAYER_BLACK, scale, hit)
        _draw_row(surface, fonts, theme, row, data, white_ply, PLAYER_WHITE, scale, hit)
    surface.set_clip(None)

    draw_scrollbar(
        surface,
        theme,
        Rect(rect.right - int(8 * scale), list_top, int(5 * scale), list_rect.h),
        scroll,
        content_height,
        list_rect.h,
    )

    footer_y = rect.bottom - footer_height
    if data.hint and data.show_hint:
        draw_text(
            surface,
            fonts,
            fit_text(fonts, data.hint, "tiny", rect.w - 2 * padding),
            (rect.x + padding, footer_y + int(6 * scale)),
            "tiny",
            theme.accent,
        )
    if data.footer:
        draw_text(
            surface,
            fonts,
            fit_text(fonts, data.footer, "tiny", rect.w - 2 * padding),
            (rect.x + padding, footer_y + int(24 * scale)),
            "tiny",
            theme.text_dim,
        )
    return hit


def _draw_row(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    row: Rect,
    data: SidebarData,
    ply: int,
    player: int,
    scale: float,
    hit: SidebarHit,
) -> None:
    if ply <= 0 or ply > len(data.records):
        return
    record = data.records[ply - 1]
    number_width = int(24 * scale)
    column_width = (row.w - number_width) // 2

    if player == PLAYER_BLACK:
        cell = Rect(row.x, row.y, number_width + column_width, row.h)
        draw_text(
            surface,
            fonts,
            f"{ply}.",
            (row.x + int(4 * scale), row.centery),
            "tiny",
            theme.text_dim,
            anchor="midleft",
        )
        text_x = row.x + number_width
    else:
        cell = Rect(row.x + number_width + column_width, row.y, column_width, row.h)
        text_x = cell.x

    selected = data.selected_ply == ply
    if selected:
        pg.draw.rect(
            surface, shade(theme.accent, 0.45), cell.as_tuple(), border_radius=3
        )

    label = record.notation
    color = theme.text if selected else theme.text_dim
    if data.review is not None:
        assessment = data.review.assessment_for(ply)
        if assessment is not None:
            color = LABEL_COLORS.get(assessment.label, color)
            if assessment.label in (MISTAKE, BLUNDER):
                label = f"{record.notation} {assessment.label[0]}"
    if ply == len(data.records):
        color = theme.accent

    marker_center = (text_x + int(5 * scale), cell.centery)
    if player == PLAYER_BLACK:
        pg.draw.circle(surface, theme.black_body, marker_center, int(3 * scale))
    else:
        pg.draw.circle(surface, theme.white_body, marker_center, int(3 * scale))
        pg.draw.circle(surface, theme.white_rim, marker_center, int(3 * scale), 1)

    draw_text(
        surface,
        fonts,
        label,
        (text_x + int(12 * scale), cell.centery),
        "small",
        color,
        anchor="midleft",
        bold=selected,
    )
    hit.rows.append((cell, ply))


def _draw_graph(
    surface: pg.Surface,
    fonts: FontBook,
    theme: Theme,
    rect: Rect,
    data: SidebarData,
    scale: float,
) -> None:
    pg.draw.rect(surface, shade(theme.panel, 0.85), rect.as_tuple(), border_radius=4)
    mid_y = rect.centery
    pg.draw.line(
        surface,
        shade(theme.panel_border, 0.7),
        (rect.x + 4, mid_y),
        (rect.right - 4, mid_y),
    )

    probabilities = [record.probability_black for record in data.records]
    if not probabilities:
        draw_text(
            surface,
            fonts,
            "No moves yet",
            rect.center,
            "tiny",
            theme.text_dim,
            anchor="center",
        )
        return

    points = []
    count = max(1, len(probabilities) - 1)
    for index, probability in enumerate(probabilities):
        t = index / count if count else 1.0
        x = rect.x + 4 + int((rect.w - 8) * t)
        y = rect.bottom - 4 - int((rect.h - 8) * probability)
        points.append((x, y))

    if len(points) > 1:
        area = points + [
            (points[-1][0], rect.bottom - 4),
            (points[0][0], rect.bottom - 4),
        ]
        shade_surface = pg.Surface(rect.size, pg.SRCALPHA)
        local = [(x - rect.x, y - rect.y) for x, y in area]
        pg.draw.polygon(shade_surface, (*theme.accent_soft, 42), local)
        surface.blit(shade_surface, rect.topleft)
        pg.draw.lines(surface, theme.accent, False, points, max(1, int(1.5 * scale)))

    pg.draw.circle(surface, theme.accent, points[-1], max(2, int(3 * scale)))


__all__ = ["LABEL_COLORS", "SidebarData", "SidebarHit", "draw_sidebar"]
