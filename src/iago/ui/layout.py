"""Responsive layout.

All geometry is derived from the window size and the board size, so the
interface adapts to any window shape, to fullscreen, and to high-DPI scaling.
The calculation is a pure function, which makes it cheap to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..core.constants import DEFAULT_BOARD_SIZE

#: Design constants, expressed at a UI scale of 1.0.
MIN_CELL = 26
MAX_CELL = 96
MENUBAR_HEIGHT = 46
STATUS_HEIGHT = 132
SIDEBAR_WIDTH = 286
GUTTER = 16
FRAME = 10
MIN_WINDOW = (760, 660)
MAX_WINDOW = (2400, 1800)


@dataclass(frozen=True)
class Rect:
    """Integer rectangle with the helpers the UI needs."""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def centerx(self) -> int:
        return self.x + self.w // 2

    @property
    def centery(self) -> int:
        return self.y + self.h // 2

    @property
    def left(self) -> int:
        return self.x

    @property
    def topleft(self) -> Tuple[int, int]:
        return self.x, self.y

    @property
    def top(self) -> int:
        return self.y

    @property
    def size(self) -> Tuple[int, int]:
        return self.w, self.h

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h

    def __iter__(self):
        """Allow pygame APIs that accept a ``rectstyle`` to take a Rect."""

        return iter((self.x, self.y, self.w, self.h))

    def __len__(self) -> int:
        return 4

    def __getitem__(self, index: int) -> int:
        return (self.x, self.y, self.w, self.h)[index]

    def contains(self, point: Tuple[int, int]) -> bool:
        px, py = point
        return self.x <= px < self.right and self.y <= py < self.bottom

    def inset(self, dx: int, dy: Optional[int] = None) -> "Rect":
        dy = dx if dy is None else dy
        return Rect(
            self.x + dx, self.y + dy, max(0, self.w - 2 * dx), max(0, self.h - 2 * dy)
        )

    def moved(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def scaled(self, factor: float) -> "Rect":
        return Rect(
            int(self.x * factor),
            int(self.y * factor),
            max(1, int(self.w * factor)),
            max(1, int(self.h * factor)),
        )


@dataclass(frozen=True)
class Layout:
    """Resolved geometry for one window size."""

    width: int
    height: int
    board_size: int
    cell: int
    menubar: Rect
    board: Rect
    frame: Rect
    sidebar: Optional[Rect]
    status: Rect
    ui_scale: float

    @property
    def board_px(self) -> int:
        return self.cell * self.board_size

    @property
    def size(self) -> Tuple[int, int]:
        return self.width, self.height

    def cell_rect(self, row: int, col: int) -> Rect:
        return Rect(
            self.board.x + col * self.cell,
            self.board.y + row * self.cell,
            self.cell,
            self.cell,
        )

    def cell_center(self, row: int, col: int) -> Tuple[int, int]:
        return (
            self.board.x + col * self.cell + self.cell // 2,
            self.board.y + row * self.cell + self.cell // 2,
        )

    def hit_cell(self, point: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Convert a window point into ``(row, col)`` or ``None``."""

        if not self.board.contains(point):
            return None
        col = (point[0] - self.board.x) // self.cell
        row = (point[1] - self.board.y) // self.cell
        if 0 <= row < self.board_size and 0 <= col < self.board_size:
            return int(row), int(col)
        return None

    def scaled(self, factor: float) -> "Layout":
        """Return the same layout multiplied by *factor* (for HiDPI blits)."""

        return Layout(
            width=int(self.width * factor),
            height=int(self.height * factor),
            board_size=self.board_size,
            cell=max(1, int(self.cell * factor)),
            menubar=self.menubar.scaled(factor),
            board=self.board.scaled(factor),
            frame=self.frame.scaled(factor),
            sidebar=None if self.sidebar is None else self.sidebar.scaled(factor),
            status=self.status.scaled(factor),
            ui_scale=self.ui_scale,
        )


def clamp_window(size: Tuple[int, int]) -> Tuple[int, int]:
    width = max(MIN_WINDOW[0], min(MAX_WINDOW[0], int(size[0])))
    height = max(MIN_WINDOW[1], min(MAX_WINDOW[1], int(size[1])))
    return width, height


def compute_layout(
    window_size: Tuple[int, int],
    board_size: int = DEFAULT_BOARD_SIZE,
    ui_scale: float = 1.0,
) -> Layout:
    """Compute the full layout for a window of *window_size* pixels."""

    width, height = clamp_window(window_size)
    ui_scale = max(0.75, min(2.0, ui_scale))

    menubar_h = int(MENUBAR_HEIGHT * ui_scale)
    status_h = int(STATUS_HEIGHT * ui_scale)
    gutter = int(GUTTER * ui_scale)
    frame = int(FRAME * ui_scale)
    sidebar_w = int(SIDEBAR_WIDTH * ui_scale)

    menubar = Rect(0, 0, width, menubar_h)
    status = Rect(0, height - status_h, width, status_h)

    show_sidebar = width >= int(1024 * ui_scale)
    side = sidebar_w if show_sidebar else 0

    available_w = (
        width - 2 * gutter - (sidebar_w + gutter if show_sidebar else 0) - 2 * frame
    )
    available_h = height - menubar_h - status_h - 2 * gutter - 2 * frame
    cell = min(available_w // board_size, available_h // board_size)
    cell = max(MIN_CELL, min(MAX_CELL, cell))

    board_px = cell * board_size
    frame_rect_w = board_px + 2 * frame
    frame_rect_h = board_px + 2 * frame

    content_x = gutter
    content_w = width - 2 * gutter
    frame_x = (
        content_x
        + (content_w - (frame_rect_w + (side + (gutter if show_sidebar else 0)))) // 2
    )
    if frame_x < gutter:
        frame_x = gutter
    frame_y = menubar_h + gutter + max(0, (available_h + 2 * frame - frame_rect_h) // 2)

    frame_rect = Rect(frame_x, frame_y, frame_rect_w, frame_rect_h)
    board = Rect(frame_x + frame, frame_y + frame, board_px, board_px)

    sidebar: Optional[Rect] = None
    if show_sidebar:
        sidebar = Rect(
            frame_rect.right + gutter,
            frame_rect.y,
            width - frame_rect.right - 2 * gutter,
            min(frame_rect.h, status.y - frame_rect.y - gutter),
        )

    return Layout(
        width=width,
        height=height,
        board_size=board_size,
        cell=cell,
        menubar=menubar,
        board=board,
        frame=frame_rect,
        sidebar=sidebar,
        status=status,
        ui_scale=ui_scale,
    )


def centered_panel(layout: Layout, width: int, height: int) -> Rect:
    """Return a centred panel rectangle clamped to the window."""

    width = min(width, layout.width - 2 * int(20 * layout.ui_scale))
    height = min(height, layout.height - 2 * int(20 * layout.ui_scale))
    return Rect(
        (layout.width - width) // 2,
        (layout.height - height) // 2,
        width,
        height,
    )


__all__ = [
    "GUTTER",
    "Layout",
    "MAX_CELL",
    "MIN_CELL",
    "MIN_WINDOW",
    "Rect",
    "clamp_window",
    "centered_panel",
    "compute_layout",
]
