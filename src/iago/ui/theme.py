"""Colour themes.

Every visual constant the renderer needs lives in a :class:`Theme`.  Themes are
pure data (no pygame import) so they can be unit-tested and reused by tools.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Tuple

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    """A complete visual identity for the board and the chrome around it."""

    key: str
    name: str
    dark: bool

    # Board
    board_light: Color
    board_dark: Color
    grid_line: Color
    frame: Color
    frame_edge: Color
    texture: str  # "felt" | "wood" | "linen" | "none"

    # Discs
    black_base: Color
    black_body: Color
    black_rim: Color
    black_shine: Color
    white_base: Color
    white_body: Color
    white_rim: Color
    white_shine: Color

    # Chrome
    background: Color
    background_deep: Color
    panel: Color
    panel_raised: Color
    panel_border: Color
    text: Color
    text_dim: Color
    text_inverse: Color
    accent: Color
    accent_soft: Color
    good: Color
    warn: Color
    bad: Color

    # Board furniture
    hint: Color
    hint_best: Color
    last_move: Color
    preview: Color
    coordinate: Color
    eval_black: Color
    eval_white: Color
    marker_style: str = "dots"  # "dots" | "shapes"

    def mixed(self, **changes: object) -> "Theme":
        """Return a copy with some fields replaced."""

        return replace(self, **changes)  # type: ignore[arg-type]


CLASSIC = Theme(
    key="classic",
    name="Classic",
    dark=True,
    board_light=(48, 141, 90),
    board_dark=(38, 122, 76),
    grid_line=(26, 88, 56),
    frame=(96, 66, 40),
    frame_edge=(58, 38, 22),
    texture="felt",
    black_base=(28, 29, 33),
    black_body=(52, 54, 61),
    black_rim=(14, 15, 17),
    black_shine=(150, 154, 168),
    white_base=(226, 224, 214),
    white_body=(250, 249, 244),
    white_rim=(168, 166, 156),
    white_shine=(255, 255, 255),
    background=(24, 26, 30),
    background_deep=(16, 17, 20),
    panel=(34, 37, 43),
    panel_raised=(43, 47, 55),
    panel_border=(62, 67, 78),
    text=(238, 239, 242),
    text_dim=(154, 160, 172),
    text_inverse=(20, 22, 26),
    accent=(255, 190, 64),
    accent_soft=(150, 112, 40),
    good=(96, 200, 128),
    warn=(232, 178, 72),
    bad=(226, 96, 96),
    hint=(120, 214, 255),
    hint_best=(255, 206, 84),
    last_move=(255, 214, 92),
    preview=(148, 226, 170),
    coordinate=(180, 205, 190),
    eval_black=(88, 92, 108),
    eval_white=(224, 222, 212),
)

WOOD = Theme(
    key="wood",
    name="Walnut",
    dark=True,
    board_light=(214, 176, 122),
    board_dark=(196, 156, 104),
    grid_line=(122, 88, 54),
    frame=(84, 52, 30),
    frame_edge=(52, 31, 18),
    texture="wood",
    black_base=(34, 28, 24),
    black_body=(62, 50, 42),
    black_rim=(18, 14, 11),
    black_shine=(158, 136, 116),
    white_base=(232, 222, 200),
    white_body=(252, 246, 232),
    white_rim=(176, 162, 138),
    white_shine=(255, 253, 246),
    background=(32, 27, 24),
    background_deep=(22, 18, 16),
    panel=(45, 38, 33),
    panel_raised=(56, 47, 40),
    panel_border=(80, 68, 57),
    text=(240, 234, 224),
    text_dim=(166, 152, 136),
    text_inverse=(28, 22, 18),
    accent=(226, 168, 86),
    accent_soft=(128, 92, 46),
    good=(126, 190, 120),
    warn=(224, 170, 80),
    bad=(214, 104, 88),
    hint=(150, 214, 236),
    hint_best=(255, 196, 92),
    last_move=(255, 206, 110),
    preview=(196, 224, 160),
    coordinate=(128, 100, 68),
    eval_black=(74, 58, 46),
    eval_white=(232, 220, 198),
)

OCEAN = Theme(
    key="ocean",
    name="Ocean",
    dark=True,
    board_light=(32, 96, 148),
    board_dark=(24, 80, 128),
    grid_line=(16, 58, 96),
    frame=(18, 36, 54),
    frame_edge=(9, 20, 32),
    texture="felt",
    black_base=(20, 28, 40),
    black_body=(38, 52, 72),
    black_rim=(10, 15, 22),
    black_shine=(120, 162, 198),
    white_base=(214, 230, 240),
    white_body=(242, 250, 255),
    white_rim=(150, 176, 194),
    white_shine=(255, 255, 255),
    background=(14, 24, 34),
    background_deep=(8, 15, 22),
    panel=(20, 34, 47),
    panel_raised=(27, 45, 61),
    panel_border=(40, 68, 92),
    text=(232, 242, 250),
    text_dim=(140, 166, 188),
    text_inverse=(10, 20, 30),
    accent=(90, 200, 255),
    accent_soft=(40, 110, 150),
    good=(96, 214, 190),
    warn=(236, 190, 90),
    bad=(236, 110, 110),
    hint=(140, 226, 255),
    hint_best=(255, 212, 100),
    last_move=(120, 220, 255),
    preview=(140, 220, 240),
    coordinate=(150, 190, 215),
    eval_black=(32, 44, 58),
    eval_white=(224, 238, 246),
)

SUNSET = Theme(
    key="sunset",
    name="Sunset",
    dark=True,
    board_light=(198, 112, 92),
    board_dark=(172, 88, 78),
    grid_line=(128, 62, 62),
    frame=(74, 42, 52),
    frame_edge=(44, 24, 32),
    texture="linen",
    black_base=(38, 26, 34),
    black_body=(64, 44, 52),
    black_rim=(20, 13, 18),
    black_shine=(170, 120, 118),
    white_base=(244, 226, 210),
    white_body=(255, 246, 236),
    white_rim=(188, 162, 148),
    white_shine=(255, 255, 250),
    background=(32, 24, 30),
    background_deep=(21, 15, 20),
    panel=(46, 34, 42),
    panel_raised=(58, 43, 52),
    panel_border=(86, 62, 72),
    text=(248, 238, 236),
    text_dim=(184, 154, 154),
    text_inverse=(30, 18, 24),
    accent=(255, 152, 112),
    accent_soft=(150, 78, 62),
    good=(142, 200, 140),
    warn=(248, 176, 96),
    bad=(240, 112, 112),
    hint=(255, 214, 170),
    hint_best=(255, 226, 130),
    last_move=(255, 196, 120),
    preview=(255, 208, 176),
    coordinate=(240, 200, 186),
    eval_black=(58, 38, 46),
    eval_white=(246, 228, 212),
)

FOREST = Theme(
    key="forest",
    name="Forest",
    dark=True,
    board_light=(58, 112, 72),
    board_dark=(46, 94, 60),
    grid_line=(32, 70, 44),
    frame=(58, 44, 30),
    frame_edge=(34, 25, 17),
    texture="wood",
    black_base=(24, 30, 26),
    black_body=(44, 54, 46),
    black_rim=(12, 17, 14),
    black_shine=(136, 156, 138),
    white_base=(224, 228, 208),
    white_body=(246, 250, 238),
    white_rim=(164, 172, 152),
    white_shine=(255, 255, 250),
    background=(20, 27, 22),
    background_deep=(13, 18, 15),
    panel=(28, 39, 32),
    panel_raised=(37, 51, 42),
    panel_border=(56, 76, 62),
    text=(232, 240, 230),
    text_dim=(150, 168, 152),
    text_inverse=(16, 24, 18),
    accent=(148, 214, 120),
    accent_soft=(72, 116, 64),
    good=(150, 220, 140),
    warn=(232, 196, 96),
    bad=(224, 108, 96),
    hint=(168, 232, 200),
    hint_best=(250, 226, 120),
    last_move=(250, 230, 140),
    preview=(190, 232, 176),
    coordinate=(178, 200, 178),
    eval_black=(34, 44, 36),
    eval_white=(226, 232, 212),
)

MIDNIGHT = Theme(
    key="midnight",
    name="Midnight",
    dark=True,
    board_light=(52, 56, 70),
    board_dark=(43, 47, 60),
    grid_line=(28, 31, 41),
    frame=(20, 22, 29),
    frame_edge=(11, 12, 16),
    texture="none",
    black_base=(16, 17, 22),
    black_body=(34, 36, 46),
    black_rim=(8, 9, 12),
    black_shine=(120, 126, 150),
    white_base=(216, 220, 236),
    white_body=(242, 245, 255),
    white_rim=(154, 158, 176),
    white_shine=(255, 255, 255),
    background=(13, 14, 19),
    background_deep=(8, 9, 12),
    panel=(24, 26, 34),
    panel_raised=(32, 35, 45),
    panel_border=(50, 54, 68),
    text=(230, 234, 246),
    text_dim=(142, 148, 168),
    text_inverse=(14, 15, 20),
    accent=(150, 160, 255),
    accent_soft=(70, 76, 140),
    good=(110, 210, 190),
    warn=(236, 190, 100),
    bad=(232, 104, 116),
    hint=(140, 190, 255),
    hint_best=(190, 200, 255),
    last_move=(160, 170, 255),
    preview=(150, 200, 255),
    coordinate=(150, 156, 180),
    eval_black=(30, 32, 42),
    eval_white=(224, 228, 242),
)

HIGH_CONTRAST = Theme(
    key="contrast",
    name="High Contrast",
    dark=True,
    board_light=(252, 252, 252),
    board_dark=(26, 26, 26),
    grid_line=(0, 0, 0),
    frame=(12, 12, 12),
    frame_edge=(0, 0, 0),
    texture="none",
    black_base=(0, 0, 0),
    black_body=(18, 18, 18),
    black_rim=(0, 0, 0),
    black_shine=(90, 90, 90),
    white_base=(255, 255, 255),
    white_body=(255, 255, 255),
    white_rim=(0, 0, 0),
    white_shine=(255, 255, 255),
    background=(0, 0, 0),
    background_deep=(0, 0, 0),
    panel=(12, 12, 12),
    panel_raised=(24, 24, 24),
    panel_border=(255, 255, 255),
    text=(255, 255, 255),
    text_dim=(214, 214, 214),
    text_inverse=(0, 0, 0),
    accent=(255, 232, 0),
    accent_soft=(180, 160, 0),
    good=(0, 255, 128),
    warn=(255, 200, 0),
    bad=(255, 96, 96),
    hint=(0, 220, 255),
    hint_best=(255, 232, 0),
    last_move=(255, 232, 0),
    preview=(0, 255, 128),
    coordinate=(255, 255, 255),
    eval_black=(60, 60, 60),
    eval_white=(240, 240, 240),
    marker_style="shapes",
)

THEMES: Dict[str, Theme] = {
    theme.key: theme
    for theme in (
        CLASSIC,
        WOOD,
        OCEAN,
        SUNSET,
        FOREST,
        MIDNIGHT,
        HIGH_CONTRAST,
    )
}

THEME_ORDER: Tuple[str, ...] = tuple(THEMES)
DEFAULT_THEME_KEY = CLASSIC.key


def get_theme(key: str) -> Theme:
    """Return the theme registered under *key*, falling back to the default."""

    return THEMES.get(key, THEMES[DEFAULT_THEME_KEY])


def next_theme(key: str) -> str:
    """Return the key of the theme after *key* in display order."""

    keys = THEME_ORDER
    try:
        index = keys.index(key)
    except ValueError:
        return DEFAULT_THEME_KEY
    return keys[(index + 1) % len(keys)]


__all__ = [
    "Color",
    "DEFAULT_THEME_KEY",
    "HIGH_CONTRAST",
    "THEMES",
    "THEME_ORDER",
    "Theme",
    "get_theme",
    "next_theme",
]
