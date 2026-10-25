"""Frame composition.

The renderer owns every cached surface and animation, so the controller only
has to describe *what* to show through :class:`RenderModel`.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pygame as pg

from ..ai.evaluation import win_probability
from ..ai.search import SearchResult
from ..app.analysis import GameReview
from ..app.session import MoveRecord, Session
from ..app.settings import GameStats
from ..branding import APP_NAME, VERSION
from ..core.board import Board
from ..core.constants import (
    COLUMN_LETTERS,
    EMPTY,
    MODE_LABELS,
    PLAYER_BLACK,
    PLAYER_WHITE,
)
from .animation import (
    AnimatedValue,
    AnimationManager,
    ParticleSystem,
    ScreenShake,
    ToastStack,
    ease_out_back,
)
from .assets import DiscCache, FontBook, TextureCache, make_window_icon, mix, shade
from .drawing import draw_diamond, draw_glow, draw_ring, draw_star, draw_text, gradient
from .hud import StatusData, build_menubar, draw_menubar, draw_status
from .layout import Rect, compute_layout
from .overlays import (
    ClickTarget,
    GameOverData,
    OptionsData,
    ResumeData,
    draw_game_over,
    draw_help,
    draw_options,
    draw_resume,
    draw_stats,
)
from .sidebar import SidebarData, SidebarHit, draw_sidebar
from .theme import Color, Theme
from .widgets import Button, draw_tooltip


@dataclass
class RenderModel:
    """Everything the renderer needs for one frame."""

    session: Session
    theme: Theme
    hint_move: Optional[Tuple[int, int]] = None
    show_hints: bool = True
    hover_cell: Optional[Tuple[int, int]] = None
    hover_legal: bool = False
    thinking: Optional[SearchResult] = None
    thinking_text: str = ""
    message: str = ""
    message_color: Optional[Color] = None
    banner: Optional[str] = None
    banner_color: Optional[Color] = None
    overlay: Optional[str] = None
    overlay_data: Any = None
    selected_ply: Optional[int] = None
    display_board: Optional[Board] = None
    review: Optional[GameReview] = None
    sidebar_scroll: int = 0
    sidebar_footer: str = ""
    hint_text: str = ""
    mouse: Optional[Tuple[int, int]] = None
    pressed_button: Optional[str] = None
    show_coordinates: bool = True
    show_eval_bar: bool = True
    animations_enabled: bool = True
    particles_enabled: bool = True
    debug: bool = False
    fps: float = 0.0
    badge: str = ""
    game_over_reason: str = "board"
    review_progress: Tuple[int, int] = (0, 0)
    new_achievements: Sequence[str] = ()
    paused: bool = False
    stats: Optional[GameStats] = None


class Renderer:
    """Draws the whole interface and publishes click targets."""

    def __init__(
        self,
        window_size: Tuple[int, int],
        board_size: int,
        theme: Theme,
        ui_scale: float = 1.0,
    ) -> None:
        self.fonts = FontBook(ui_scale)
        self.discs = DiscCache()
        self.textures = TextureCache()
        self.animations = AnimationManager()
        self.particles = ParticleSystem()
        self.toasts = ToastStack()
        self.shake = ScreenShake()
        self.score_black = AnimatedValue(2)
        self.score_white = AnimatedValue(2)
        self.ui_scale = ui_scale
        self.theme = theme
        self.board_size = board_size
        self.layout = compute_layout(window_size, board_size, ui_scale)
        self.surface = pg.display.set_mode(
            (self.layout.width, self.layout.height), pg.RESIZABLE
        )
        self._plate: Optional[pg.Surface] = None
        self._plate_key: Tuple[Any, ...] = ()
        self._flip_from: Dict[Tuple[int, int], int] = {}
        self._last_now = time.monotonic()
        self._particles_on = True
        self.targets: List[ClickTarget] = []
        self.menubar_buttons: List[Button] = []
        self.sidebar_hit: Optional[SidebarHit] = None
        self._background: Optional[pg.Surface] = None
        self._background_key: Tuple[Any, ...] = ()
        try:
            pg.display.set_icon(make_window_icon(theme))
        except pg.error:  # pragma: no cover - headless environments
            pass

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def resize(self, size: Tuple[int, int]) -> None:
        self.layout = compute_layout(size, self.board_size, self.ui_scale)
        self.surface = pg.display.set_mode(
            (self.layout.width, self.layout.height), pg.RESIZABLE
        )
        self._plate = None
        self._background = None

    def set_theme(self, theme: Theme) -> None:
        if theme.key == self.theme.key:
            return
        self.theme = theme
        self.discs.clear()
        self._plate = None
        self._background = None
        try:
            pg.display.set_icon(make_window_icon(theme))
        except pg.error:  # pragma: no cover
            pass

    def set_board_size(self, size: int) -> None:
        if size == self.board_size:
            return
        self.board_size = size
        self.layout = compute_layout(self.layout.size, size, self.ui_scale)
        self._plate = None
        self._background = None
        self.animations.clear()

    def set_ui_scale(self, scale: float) -> None:
        self.ui_scale = scale
        self.fonts.scale = scale
        self.fonts.clear()
        self.layout = compute_layout(self.layout.size, self.board_size, scale)
        self._plate = None
        self._background = None

    # ------------------------------------------------------------------
    # Animation hooks
    # ------------------------------------------------------------------

    def animate_move(self, record: MoveRecord, now: Optional[float] = None) -> None:
        now = self._now() if now is None else now
        self.animations.add(("place", record.row, record.col), now, 0.18, "back")
        for row, col in record.flips:
            distance = abs(row - record.row) + abs(col - record.col)
            self._flip_from[(row, col)] = 3 - record.player
            self.animations.add(
                ("flip", row, col), now, 0.20, "cubic", delay=0.05 * distance
            )
            if self.particles_enabled():
                cx, cy = self.layout.cell_center(row, col)
                colour = (
                    self.theme.white_shine
                    if record.player == PLAYER_WHITE
                    else self.theme.black_shine
                )
                self.particles.emit_burst(
                    cx,
                    cy,
                    colour,
                    count=max(2, 6 - distance),
                    speed=70,
                    life=0.35,
                    size=2.0,
                )
        if len(record.flips) >= 6:
            self.shake.trigger(now, amplitude=3.0, duration=0.18)
        self.score_black.set(record.black_score)
        self.score_white.set(record.white_score)

    def celebrate(self, winner: Optional[int], now: Optional[float] = None) -> None:
        if not self.particles_enabled():
            return
        now = self._now() if now is None else now
        colours = [
            self.theme.accent,
            self.theme.good,
            self.theme.white_body,
            self.theme.hint,
        ]
        self.particles.emit_confetti(
            (self.layout.board.x, self.layout.board.y, self.layout.board.w, 40),
            colours,
            count=90,
        )

    def sync_scores(self, black: int, white: int) -> None:
        """Snap the score counters (used when history changes without a move)."""

        self.score_black.snap(black)
        self.score_white.snap(white)

    def notify(self, text: str, color: Optional[Color] = None) -> None:
        self.toasts.push(text, color or self.theme.accent, self._now())

    def particles_enabled(self) -> bool:
        return self._particles_on

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt: float, now: Optional[float] = None) -> None:
        now = self._now() if now is None else now
        self.particles.update(dt)
        self.animations.prune(now)
        self.score_black.update(dt)
        self.score_white.update(dt)
        self._last_now = now

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, model: RenderModel, now: Optional[float] = None) -> None:
        now = self._now() if now is None else now
        self.theme = model.theme
        self._particles_on = model.particles_enabled
        black, white = model.session.score()
        if abs(self.score_black.target - black) > 10:
            self.score_black.snap(black)
        if abs(self.score_white.target - white) > 10:
            self.score_white.snap(white)
        self.targets.clear()
        surface = self.surface

        self._draw_background(surface)

        self.menubar_buttons = build_menubar(self.layout, model.session)
        hovered = self._hovered_key(
            model.mouse, [button.rect for button in self.menubar_buttons]
        )
        hovered_key = None
        if hovered is not None:
            hovered_key = self.menubar_buttons[hovered].key
        draw_menubar(
            surface,
            self.fonts,
            self.theme,
            self.layout,
            self.menubar_buttons,
            APP_NAME,
            hovered=hovered_key,
            pressed=model.pressed_button,
            badge=f"v{VERSION}",
        )
        for button in self.menubar_buttons:
            self.targets.append(
                ClickTarget(button.rect, "button", button.key, button.tooltip)
            )

        self._draw_board(surface, model, now)
        self._draw_sidebar(surface, model)
        self._draw_status(surface, model)
        self._draw_toasts(surface, now)

        if model.debug:
            self._draw_debug(surface, model)

        self._draw_overlay(surface, model)
        self._draw_tools(surface, model)
        pg.display.flip()

    # -- background -----------------------------------------------------

    def _draw_background(self, surface: pg.Surface) -> None:
        key = (self.theme.key, self.layout.width, self.layout.height)
        if self._background is None or self._background_key != key:
            backdrop = gradient(
                (self.layout.width, self.layout.height),
                mix(self.theme.background, self.theme.background_deep, 0.25),
                self.theme.background_deep,
            ).copy()
            surface.blit(backdrop, (0, 0))
            self._background = backdrop
            self._background_key = key
        else:
            surface.blit(self._background, (0, 0))

    # -- board ----------------------------------------------------------

    def _draw_board(self, surface: pg.Surface, model: RenderModel, now: float) -> None:
        layout = self.layout
        board = model.display_board or model.session.board
        plate = self._plate_surface(model.show_coordinates)
        shake_x, shake_y = self.shake.offset(now)
        surface.blit(plate, (layout.frame.x + shake_x, layout.frame.y + shake_y))

        session = model.session
        interactive = (
            model.display_board is None
            and not session.game_over
            and model.overlay is None
        )

        # Hover preview tint in the cells that would flip.
        if interactive and model.hover_cell and model.show_hints:
            hover = model.hover_cell
            if (
                board.is_valid_move(hover[0], hover[1], board.current_player)
                and session.is_human_turn()
            ):
                tint = pg.Surface((layout.cell, layout.cell), pg.SRCALPHA)
                tint.fill((*self.theme.preview, 84))
                for row, col in board.get_flips(
                    hover[0], hover[1], board.current_player
                ):
                    rect = layout.cell_rect(row, col)
                    surface.blit(tint, (rect.x + shake_x, rect.y + shake_y))

        self._draw_pieces(surface, board, now, shake_x, shake_y, model)

        last_move = session.last_move if model.display_board is None else None
        if last_move is not None:
            row, col = last_move
            cx, cy = layout.cell_center(row, col)
            pulse = 0.5 + 0.5 * math.sin(now * 4.0)
            radius = int(layout.cell * 0.47 + layout.cell * 0.02 * pulse)
            draw_ring(
                surface,
                (cx + shake_x, cy + shake_y),
                radius,
                self.theme.last_move,
                max(2, int(layout.cell * 0.04)),
            )

        if interactive and model.show_hints and session.is_human_turn():
            self._draw_move_markers(surface, board, model)

        if interactive and model.hover_cell:
            hover = model.hover_cell
            if (
                board.is_valid_move(hover[0], hover[1], board.current_player)
                and session.is_human_turn()
            ):
                cx, cy = layout.cell_center(hover[0], hover[1])
                radius = int(layout.cell * 0.42)
                ghost = self.discs.ghost(self.theme, board.current_player, radius, 130)
                surface.blit(
                    ghost, (cx - ghost.get_width() // 2, cy - ghost.get_height() // 2)
                )

        if model.particles_enabled:
            self.particles.draw(surface)

    def _draw_pieces(
        self,
        surface: pg.Surface,
        board: Board,
        now: float,
        shake_x: int,
        shake_y: int,
        model: RenderModel,
    ) -> None:
        layout = self.layout
        base_radius = max(4, int(layout.cell * 0.5) - max(2, int(layout.cell * 0.055)))
        animate = model.animations_enabled and model.display_board is None

        for row in range(board.size):
            for col in range(board.size):
                piece = board.grid[row][col]
                if piece == EMPTY:
                    continue
                cx, cy = layout.cell_center(row, col)
                cx += shake_x
                cy += shake_y
                radius = base_radius
                x_scale = 1.0
                player = piece

                if animate:
                    place_key = ("place", row, col)
                    if self.animations.active(place_key, now):
                        progress = self.animations.progress(place_key, now)
                        radius = max(1, int(base_radius * ease_out_back(progress)))
                    flip_key = ("flip", row, col)
                    if self.animations.active(flip_key, now):
                        progress = self.animations.progress(flip_key, now)
                        x_scale = abs(math.cos(math.pi * progress))
                        player = (
                            self._flip_from.get((row, col), piece)
                            if progress < 0.5
                            else piece
                        )

                if radius <= 1:
                    continue
                sprite = self.discs.get(self.theme, player, radius)
                width = max(2, int(sprite.get_width() * x_scale))
                if width != sprite.get_width():
                    sprite = pg.transform.smoothscale(
                        sprite, (width, sprite.get_height())
                    )
                surface.blit(
                    sprite,
                    (cx - sprite.get_width() // 2, cy - sprite.get_height() // 2),
                )

    def _draw_move_markers(
        self, surface: pg.Surface, board: Board, model: RenderModel
    ) -> None:
        layout = self.layout
        moves = board.get_valid_moves(board.current_player)
        shapes = self.theme.marker_style == "shapes"
        for row, col in moves:
            cx, cy = layout.cell_center(row, col)
            is_best = model.hint_move == (row, col)
            if is_best:
                radius = int(layout.cell * 0.30)
                draw_glow(
                    surface,
                    (cx, cy),
                    int(layout.cell * 0.42),
                    self.theme.hint_best,
                    alpha=110,
                )
                if shapes:
                    draw_diamond(surface, (cx, cy), radius, self.theme.hint_best)
                else:
                    draw_star(surface, (cx, cy), radius, self.theme.hint_best)
                if not shapes:
                    draw_ring(
                        surface, (cx, cy), radius, shade(self.theme.hint_best, 0.65), 2
                    )
            else:
                if shapes:
                    size = max(4, int(layout.cell * 0.11))
                    pg.draw.rect(
                        surface,
                        self.theme.hint,
                        (cx - size, cy - size, size * 2, size * 2),
                        1,
                        border_radius=1,
                    )
                else:
                    pg.draw.circle(
                        surface,
                        shade(self.theme.hint, 0.55),
                        (cx, cy),
                        max(3, int(layout.cell * 0.11)),
                    )
                    pg.draw.circle(
                        surface,
                        self.theme.hint,
                        (cx, cy),
                        max(2, int(layout.cell * 0.07)),
                    )
                    pg.draw.circle(
                        surface,
                        mix(self.theme.hint, (255, 255, 255), 0.5),
                        (cx, cy),
                        max(1, int(layout.cell * 0.035)),
                    )

    def _plate_surface(self, show_coordinates: bool) -> pg.Surface:
        key = (
            self.theme.key,
            self.layout.cell,
            self.board_size,
            show_coordinates,
        )
        if self._plate is not None and self._plate_key == key:
            return self._plate

        layout = self.layout
        theme = self.theme
        size = (layout.frame.w, layout.frame.h)
        plate = pg.Surface(size, pg.SRCALPHA)
        plate.fill((0, 0, 0, 0))

        # Wooden frame with bevel.
        pg.draw.rect(
            plate,
            theme.frame,
            (0, 0, size[0], size[1]),
            border_radius=int(8 * self.ui_scale),
        )
        frame_grain = self.textures.noise(
            size, "wood" if theme.texture == "wood" else "linen"
        )
        if frame_grain is not None:
            grain = frame_grain.copy()
            grain.fill((36, 36, 36), special_flags=pg.BLEND_MULT)
            plate.blit(grain, (0, 0), special_flags=pg.BLEND_RGB_ADD)
        pg.draw.rect(
            plate,
            mix(theme.frame, (255, 255, 255), 0.22),
            (1, 1, size[0] - 2, size[1] - 2),
            max(1, int(2 * self.ui_scale)),
            border_radius=int(8 * self.ui_scale),
        )
        pg.draw.rect(
            plate,
            theme.frame_edge,
            (0, 0, size[0], size[1]),
            max(1, int(1 * self.ui_scale)),
            border_radius=int(8 * self.ui_scale),
        )

        thickness = max(1, (layout.frame.w - layout.board_px) // 2)
        board_rect = pg.Rect(thickness, thickness, layout.board_px, layout.board_px)

        # Checker board with a very subtle light/dark alternation.
        for row in range(self.board_size):
            for col in range(self.board_size):
                colour = theme.board_light if (row + col) % 2 == 0 else theme.board_dark
                pg.draw.rect(
                    plate,
                    colour,
                    (
                        board_rect.x + col * layout.cell,
                        board_rect.y + row * layout.cell,
                        layout.cell,
                        layout.cell,
                    ),
                )

        board_texture = self.textures.noise(board_rect.size, theme.texture)
        if board_texture is not None:
            grain = board_texture.copy()
            grain.fill((30, 30, 30), special_flags=pg.BLEND_MULT)
            plate.blit(grain, board_rect.topleft, special_flags=pg.BLEND_RGB_ADD)

        line_width = max(1, int(self.ui_scale))
        for index in range(self.board_size + 1):
            x = board_rect.x + index * layout.cell
            y = board_rect.y + index * layout.cell
            pg.draw.line(
                plate,
                theme.grid_line,
                (x, board_rect.y),
                (x, board_rect.bottom),
                line_width,
            )
            pg.draw.line(
                plate,
                theme.grid_line,
                (board_rect.x, y),
                (board_rect.right, y),
                line_width,
            )

        pg.draw.rect(plate, theme.frame_edge, board_rect, line_width)

        if show_coordinates:
            self._draw_coordinates(plate, board_rect, thickness)

        self._plate = plate
        self._plate_key = key
        return plate

    def _draw_coordinates(
        self, plate: pg.Surface, board_rect: pg.Rect, thickness: int
    ) -> None:
        layout = self.layout
        theme = self.theme
        role = "tiny"
        for col in range(self.board_size):
            cell_x = board_rect.x + col * layout.cell
            background = theme.board_light if col % 2 == 0 else theme.board_dark
            colour = mix(
                background,
                (255, 255, 255) if sum(background) < 384 else (0, 0, 0),
                0.45,
            )
            label = self.fonts.render(COLUMN_LETTERS[col], role, colour)
            plate.blit(
                label,
                (
                    cell_x + int(4 * self.ui_scale),
                    board_rect.y + int(2 * self.ui_scale),
                ),
            )
        for row in range(self.board_size):
            cell_y = board_rect.y + row * layout.cell
            background = theme.board_light if row % 2 == 0 else theme.board_dark
            colour = mix(
                background,
                (255, 255, 255) if sum(background) < 384 else (0, 0, 0),
                0.45,
            )
            label = self.fonts.render(str(row + 1), role, colour)
            plate.blit(
                label,
                (
                    board_rect.right - label.get_width() - int(4 * self.ui_scale),
                    cell_y + int(2 * self.ui_scale),
                ),
            )

    # -- sidebar --------------------------------------------------------

    def _draw_sidebar(self, surface: pg.Surface, model: RenderModel) -> None:
        if self.layout.sidebar is None:
            self.sidebar_hit = None
            return
        data = SidebarData(
            records=model.session.records,
            opening=model.session.opening_name,
            selected_ply=model.selected_ply,
            review=model.review,
            scroll=model.sidebar_scroll,
            footer=model.sidebar_footer,
            hint=model.hint_text,
            show_hint=bool(model.hint_text),
        )
        self.sidebar_hit = draw_sidebar(
            surface, self.fonts, self.theme, self.layout, data
        )
        if self.sidebar_hit is not None:
            for rect, ply in self.sidebar_hit.rows:
                self.targets.append(ClickTarget(rect, "sidebar_ply", ply))

    # -- status ---------------------------------------------------------

    def _draw_status(self, surface: pg.Surface, model: RenderModel) -> None:
        session = model.session
        black, white = session.score()
        turn_name = "Black" if session.current_player == PLAYER_BLACK else "White"

        if session.game_over:
            if session.winner == 0:
                banner = "Draw"
            elif session.winner is not None:
                banner = (
                    f"{'Black' if session.winner == PLAYER_BLACK else 'White'} wins"
                )
            else:
                banner = "Game over"
            banner_color = self.theme.accent
            turn_player = None
        elif model.overlay == "review" or model.selected_ply is not None:
            banner = f"Reviewing move {model.selected_ply or 0}"
            banner_color = self.theme.hint
            turn_player = None
        else:
            banner = f"{turn_name} to move"
            if session.is_human_turn():
                banner += "  ·  your move"
            banner_color = self.theme.text
            turn_player = session.current_player

        mode_line = (
            f"{MODE_LABELS.get(session.mode, session.mode)}  ·  {session.level_name()}"
        )
        opening = session.opening_name

        thinking_text = ""
        thinking_detail = ""
        if model.thinking is not None:
            thinking_text = model.thinking_text or "Thinking…"
            result = model.thinking
            if result.depth:
                thinking_detail = (
                    f"depth {result.depth} · {result.nodes:,} nodes · "
                    f"{result.nps:,.0f} nps"
                )

        clock_black = clock_white = ""
        urgent = False
        if session.clock.mode != "off":
            now_monotonic = time.monotonic()
            if session.clock.mode == "blitz":
                remaining_black = (
                    session.clock.remaining(PLAYER_BLACK, now_monotonic) or 0.0
                )
                remaining_white = (
                    session.clock.remaining(PLAYER_WHITE, now_monotonic) or 0.0
                )
                clock_black = format_clock_panel(remaining_black)
                clock_white = format_clock_panel(remaining_white)
                urgent = min(remaining_black, remaining_white) < 20
            else:
                clock_black = format_clock_panel(
                    session.clock.elapsed_for(PLAYER_BLACK, now_monotonic)
                )
                clock_white = format_clock_panel(
                    session.clock.elapsed_for(PLAYER_WHITE, now_monotonic)
                )

        probability = 0.5
        if session.records:
            probability = session.records[-1].probability_black
        elif not session.game_over:
            probability = win_probability(session.board.to_position())

        data = StatusData(
            black_score=black,
            white_score=white,
            shown_black=self.score_black.rounded,
            shown_white=self.score_white.rounded,
            turn_name=turn_name,
            turn_player=turn_player,
            banner=model.banner or banner,
            banner_color=model.banner_color or banner_color,
            mode_line=mode_line,
            opening=opening,
            probability=probability,
            thinking_text=thinking_text,
            thinking_detail=thinking_detail,
            message=model.message,
            message_color=model.message_color,
            clock_black=clock_black,
            clock_white=clock_white,
            clock_urgent=urgent,
            show_eval_bar=model.show_eval_bar,
            human_turn=session.is_human_turn(),
            result=session.game_over,
        )
        draw_status(surface, self.fonts, self.theme, self.layout, data)

    # -- overlays -------------------------------------------------------

    def _draw_overlay(self, surface: pg.Surface, model: RenderModel) -> None:
        if model.overlay is None:
            return
        targets: List[ClickTarget] = []
        if model.overlay == "options" and isinstance(model.overlay_data, OptionsData):
            targets = draw_options(
                surface, self.fonts, self.theme, self.layout, model.overlay_data
            )
        elif model.overlay == "help":
            targets = draw_help(surface, self.fonts, self.theme, self.layout)
        elif model.overlay == "stats":
            targets = draw_stats(
                surface, self.fonts, self.theme, self.layout, model.stats or GameStats()
            )
        elif model.overlay == "gameover" and isinstance(
            model.overlay_data, GameOverData
        ):
            targets = draw_game_over(
                surface, self.fonts, self.theme, self.layout, model.overlay_data
            )
        elif model.overlay == "resume" and isinstance(model.overlay_data, ResumeData):
            targets = draw_resume(
                surface, self.fonts, self.theme, self.layout, model.overlay_data
            )
        self.targets.extend(targets)

    def _draw_toasts(self, surface: pg.Surface, now: float) -> None:
        toasts = self.toasts.active(now)
        y = self.layout.menubar.h + int(16 * self.ui_scale)
        for toast in toasts:
            text = self.fonts.render(toast.text, "small", toast.color, bold=True)
            rect = Rect(
                self.layout.board.centerx - text.get_width() // 2 - 14,
                y,
                text.get_width() + 28,
                text.get_height() + 12,
            )
            panel = pg.Surface((rect.w, rect.h), pg.SRCALPHA)
            pg.draw.rect(
                panel,
                (*self.theme.background_deep, 225),
                (0, 0, rect.w, rect.h),
                border_radius=8,
            )
            pg.draw.rect(
                panel, (*toast.color, 160), (0, 0, rect.w, rect.h), 1, border_radius=8
            )
            panel.set_alpha(toast.alpha(now))
            surface.blit(panel, (rect.x, rect.y))
            surface.blit(text, (rect.x + 14, rect.y + 6))
            y += rect.h + 6

    def _draw_tools(self, surface: pg.Surface, model: RenderModel) -> None:
        if model.mouse is None:
            return
        for target in self.targets:
            if target.tooltip and target.rect.contains(model.mouse):
                draw_tooltip(
                    surface,
                    self.fonts,
                    self.theme,
                    target.tooltip,
                    model.mouse,
                    Rect(0, 0, self.layout.width, self.layout.height),
                )
                break

    def _draw_debug(self, surface: pg.Surface, model: RenderModel) -> None:
        lines = [
            f"fps {model.fps:5.1f}",
            f"theme {self.theme.key}",
            f"board {self.board_size}x{self.board_size} cell {self.layout.cell}",
            f"window {self.layout.width}x{self.layout.height} "
            f"scale {self.ui_scale:.2f}",
            f"animations {len(self.animations)} particles {self.particles.count}",
        ]
        if model.thinking is not None:
            lines.append(
                f"search d{model.thinking.depth} {model.thinking.nodes:,} nodes "
                f"{model.thinking.nps:,.0f} nps"
            )
        width = max(self.fonts.measure(line, "tiny")[0] for line in lines) + 16
        panel = Rect(
            self.layout.width - width - 10,
            self.layout.menubar.h + 10,
            width,
            len(lines) * 16 + 12,
        )
        overlay = pg.Surface((panel.w, panel.h), pg.SRCALPHA)
        overlay.fill((*self.theme.background_deep, 220))
        surface.blit(overlay, (panel.x, panel.y))
        for index, line in enumerate(lines):
            draw_text(
                surface,
                self.fonts,
                line,
                (panel.x + 8, panel.y + 6 + index * 16),
                "tiny",
                self.theme.text_dim if index else self.theme.accent,
            )

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def hit_test(self, position: Tuple[int, int]) -> Optional[ClickTarget]:
        for target in reversed(self.targets):
            if target.rect.contains(position):
                return target
        return None

    def _hovered_key(
        self, mouse: Optional[Tuple[int, int]], rects: Sequence[Rect]
    ) -> Optional[int]:
        if mouse is None:
            return None
        for index, rect in enumerate(rects):
            if rect.contains(mouse):
                return index
        return None

    # ------------------------------------------------------------------

    def _now(self) -> float:
        return pg.time.get_ticks() / 1000.0


def format_clock_panel(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


__all__ = ["RenderModel", "Renderer"]
