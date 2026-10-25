"""Font discovery, supersampled disc sprites and procedural textures.

Everything expensive is generated once and cached: text surfaces, disc sprites
per (theme, colour, radius) and the whole board plate.  Supersampled rendering
(3× by default) gives real anti-aliasing without relying on extensions.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Dict, Optional, Tuple

import pygame as pg

from ..util.log import get_logger
from .theme import Color, Theme

logger = get_logger("ui.assets")

SUPERSAMPLE = 3

#: Font roles mapped to point sizes at UI scale 1.0.
FONT_SIZES = {
    "display": 34,
    "title": 26,
    "heading": 20,
    "body": 17,
    "small": 15,
    "tiny": 13,
    "mono": 15,
}

_REGULAR_CANDIDATES = (
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/gnu-free/FreeSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/Library/Fonts/Arial.ttf",
)

_BOLD_CANDIDATES = (
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)

_SCAN_DIRS = (
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.fonts",
    "~/.local/share/fonts",
)
_MAX_SCAN = 400


def _scan_for(pattern: str) -> Optional[str]:
    """Best-effort bounded scan for a font file."""

    seen = 0
    for directory in _SCAN_DIRS:
        root = Path(directory).expanduser()
        if not root.is_dir():
            continue
        try:
            for path in root.rglob(pattern):
                seen += 1
                if seen > _MAX_SCAN:
                    return None
                return str(path)
        except OSError:  # pragma: no cover - unreadable font dirs
            continue
    return None


def find_font(bold: bool = False) -> Optional[str]:
    """Return a usable TrueType path, or ``None`` for pygame's default font."""

    for candidate in _BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    pattern = "*Sans*Bold*.ttf" if bold else "*Sans*.ttf"
    found = _scan_for(pattern)
    if found is None and bold:
        found = _scan_for("DejaVuSans.ttf")
    if found is None:
        logger.info("No TrueType font found; using pygame's built-in font")
    return found


def shade(color: Color, factor: float) -> Color:
    """Lighten (factor > 1) or darken (factor < 1) a colour."""

    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
    )


def mix(first: Color, second: Color, t: float) -> Color:
    """Linear blend between two colours (``t`` 0 → first, 1 → second)."""

    t = max(0.0, min(1.0, t))
    return (
        int(first[0] + (second[0] - first[0]) * t),
        int(first[1] + (second[1] - first[1]) * t),
        int(first[2] + (second[2] - first[2]) * t),
    )


class FontBook:
    """Font loading plus a bounded cache of rendered text surfaces."""

    def __init__(self, scale: float = 1.0) -> None:
        self.scale = scale
        self.regular_path = find_font(False)
        self.bold_path = find_font(True) or self.regular_path
        self._fonts: Dict[Tuple[str, bool], pg.font.Font] = {}
        self._text_cache: Dict[Tuple[str, str, Color], pg.Surface] = {}

    def font(self, role: str = "body", bold: bool = False) -> pg.font.Font:
        key = (role, bold)
        font = self._fonts.get(key)
        if font is None:
            size = int(FONT_SIZES.get(role, FONT_SIZES["body"]) * self.scale)
            path = self.bold_path if bold else self.regular_path
            font = pg.font.Font(path, max(9, size))
            self._fonts[key] = font
        return font

    def line_height(self, role: str = "body") -> int:
        return self.font(role).get_linesize()

    def measure(
        self, text: str, role: str = "body", bold: bool = False
    ) -> Tuple[int, int]:
        return self.font(role, bold).size(text)

    def render(
        self,
        text: str,
        role: str = "body",
        color: Color = (255, 255, 255),
        bold: bool = False,
    ) -> pg.Surface:
        key = (text, f"{role}:{int(bold)}", color)
        surface = self._text_cache.get(key)
        if surface is None:
            surface = self.font(role, bold).render(text, True, color)
            if len(self._text_cache) > 512:
                self._text_cache.clear()
            self._text_cache[key] = surface
        return surface

    def clear(self) -> None:
        self._fonts.clear()
        self._text_cache.clear()


class DiscCache:
    """Supersampled disc sprites, cached per theme, colour and radius."""

    def __init__(self, supersample: int = SUPERSAMPLE) -> None:
        self.supersample = supersample
        self._cache: Dict[Tuple[str, int, int, int], pg.Surface] = {}

    def get(self, theme: Theme, player: int, radius: int) -> pg.Surface:
        radius = max(3, int(radius))
        key = (theme.key, player, radius, 255)
        surface = self._cache.get(key)
        if surface is None:
            surface = self._render(theme, player, radius, 255)
            self._cache[key] = surface
        return surface

    def ghost(
        self, theme: Theme, player: int, radius: int, alpha: int = 110
    ) -> pg.Surface:
        radius = max(3, int(radius))
        key = (theme.key, player, radius, alpha)
        surface = self._cache.get(key)
        if surface is None:
            surface = self._render(theme, player, radius, alpha)
            self._cache[key] = surface
        return surface

    def clear(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------

    def _render(self, theme: Theme, player: int, radius: int, alpha: int) -> pg.Surface:
        ss = self.supersample
        pad = 2
        size = (radius * 2 + pad * 2) * ss
        big = pg.Surface((size, size), pg.SRCALPHA)
        centre = size // 2
        big_radius = (radius) * ss

        if player == 1:  # black
            base, body = theme.black_base, theme.black_body
            rim, shine = theme.black_rim, theme.black_shine
        else:
            base, body = theme.white_base, theme.white_body
            rim, shine = theme.white_rim, theme.white_shine

        # Drop shadow.
        shadow = pg.Surface((size, size), pg.SRCALPHA)
        pg.draw.circle(
            shadow,
            (0, 0, 0, 90),
            (centre + max(1, big_radius // 8), centre + max(1, big_radius // 6)),
            big_radius,
        )
        big.blit(shadow, (0, 0))

        # Body: concentric circles give a smooth radial gradient.
        steps = max(8, min(28, big_radius // 2))
        for step in range(steps, 0, -1):
            t = step / steps
            color = mix(base, body, 1.0 - t * 0.85)
            pg.draw.circle(big, color, (centre, centre), int(big_radius * t))

        # Inner groove.
        if big_radius > 8 * ss:
            pg.draw.circle(
                big,
                shade(base, 0.86),
                (centre, centre),
                int(big_radius * 0.78),
                max(1, ss),
            )

        # Rim.
        pg.draw.circle(big, rim, (centre, centre), big_radius, max(1, ss))

        # Soft highlight towards the upper left: stacked translucent circles so
        # the falloff is smooth instead of a hard-edged blob.
        glow = pg.Surface((size, size), pg.SRCALPHA)
        glow_centre = (
            centre - int(big_radius * 0.24),
            centre - int(big_radius * 0.26),
        )
        layers = 9
        for layer in range(layers, 0, -1):
            radius_layer = max(1, int(big_radius * 0.62 * layer / layers))
            pg.draw.circle(glow, (*shine, 13), glow_centre, radius_layer)
        if big_radius > 9 * ss:
            dot_radius = max(1, int(big_radius * 0.16))
            dot_centre = (
                centre - int(big_radius * 0.34),
                centre - int(big_radius * 0.36),
            )
            pg.draw.circle(glow, (*shine, 200), dot_centre, dot_radius)
        big.blit(glow, (0, 0))

        # Bottom-right reflected light keeps the disc from looking flat.
        bounce = pg.Surface((size, size), pg.SRCALPHA)
        pg.draw.circle(
            bounce,
            (*shade(base, 1.45), 26),
            (centre + int(big_radius * 0.18), centre + int(big_radius * 0.26)),
            max(1, int(big_radius * 0.62)),
        )
        big.blit(bounce, (0, 0))

        target = (radius * 2 + pad * 2, radius * 2 + pad * 2)
        surface = pg.transform.smoothscale(big, target)
        if alpha < 255:
            surface.set_alpha(alpha)
        return surface


class TextureCache:
    """Procedural board textures and overlays."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, int, int], pg.Surface] = {}
        self._vignettes: Dict[Tuple[int, int], pg.Surface] = {}

    def noise(
        self, size: Tuple[int, int], kind: str, seed: int = 7
    ) -> Optional[pg.Surface]:
        """Return a subtle grayscale texture surface of *size*."""

        key = (kind, size[0], size[1])
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if kind == "none":
            return None

        rng = random.Random(seed)
        small_w, small_h = 96, 96
        small = pg.Surface((small_w, small_h))
        small.fill((128, 128, 128))

        if kind == "felt":
            for _ in range(700):
                x = rng.randrange(small_w)
                y = rng.randrange(small_h)
                value = 128 + rng.randint(-26, 26)
                small.set_at((x, y), (value, value, value))
            for _ in range(90):
                x = rng.randrange(small_w)
                y = rng.randrange(small_h)
                length = rng.randint(2, 5)
                value = 128 + rng.randint(-12, 12)
                pg.draw.line(small, (value, value, value), (x, y), (x + length, y + 1))
        elif kind == "wood":
            for y in range(small_h):
                wobble = math.sin(y * 0.35) * 9 + math.sin(y * 0.11) * 5
                value = int(128 + wobble + rng.randint(-7, 7))
                pg.draw.line(small, (value, value, value), (0, y), (small_w, y))
            for _ in range(60):
                x = rng.randrange(small_w)
                y = rng.randrange(small_h)
                value = 128 + rng.randint(-18, 8)
                pg.draw.line(
                    small, (value, value, value), (x, y), (x, y + rng.randint(2, 6))
                )
        elif kind == "linen":
            for x in range(0, small_w, 3):
                value = 128 + rng.randint(-9, 9)
                pg.draw.line(small, (value, value, value), (x, 0), (x, small_h))
            for y in range(0, small_h, 3):
                value = 128 + rng.randint(-9, 9)
                pg.draw.line(small, (value, value, value), (0, y), (small_w, y))

        surface = pg.transform.smoothscale(small, size)
        self._cache[key] = surface
        return surface

    def vignette(self, size: Tuple[int, int]) -> pg.Surface:
        """A soft dark edge overlay for panels."""

        cached = self._vignettes.get(size)
        if cached is not None:
            return cached
        width, height = size
        surface = pg.Surface(size, pg.SRCALPHA)
        steps = 14
        for step in range(steps):
            alpha = int(4 + step * 2.2)
            inset = step * max(1, min(width, height) // (steps * 3))
            pg.draw.rect(
                surface,
                (0, 0, 0, alpha),
                (inset, inset, max(1, width - 2 * inset), max(1, height - 2 * inset)),
                width=max(1, min(width, height) // (steps * 2)),
            )
        self._vignettes[size] = surface
        return surface

    def clear(self) -> None:
        self._cache.clear()
        self._vignettes.clear()


def make_window_icon(theme: Theme) -> pg.Surface:
    """A small procedural icon: two discs on a rounded tile."""

    size = 64
    icon = pg.Surface((size, size), pg.SRCALPHA)
    pg.draw.rect(icon, theme.panel, (0, 0, size, size), border_radius=14)
    pg.draw.rect(icon, theme.panel_border, (0, 0, size, size), 2, border_radius=14)
    pg.draw.circle(icon, theme.black_body, (24, 32), 14)
    pg.draw.circle(icon, theme.black_rim, (24, 32), 14, 2)
    pg.draw.circle(icon, theme.white_body, (42, 32), 14)
    pg.draw.circle(icon, theme.white_rim, (42, 32), 14, 2)
    pg.draw.circle(icon, theme.accent, (42, 32), 14, 1)
    return icon


__all__ = [
    "DiscCache",
    "FONT_SIZES",
    "FontBook",
    "SUPERSAMPLE",
    "TextureCache",
    "find_font",
    "make_window_icon",
    "mix",
    "shade",
]
