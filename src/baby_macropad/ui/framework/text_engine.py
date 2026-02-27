"""Centralized font loading and text fitting utilities.

Replaces the duplicated _get_font / _get_bold_font functions scattered
across icons.py, dashboard.py, and other renderers.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageDraw, ImageFont

_FONT_PATHS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_PATHS_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


@lru_cache(maxsize=32)
def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font at the given size, with caching."""
    paths = _FONT_PATHS_BOLD if bold else _FONT_PATHS_REGULAR
    for path in paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    font_sizes: tuple[int, ...] = (14, 12, 10),
    bold: bool = True,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str, int, int]:
    """Try each font size largest to smallest. Truncate with ellipsis if none fit.

    Returns: (font, final_text, text_width, text_height)
    """
    for size in font_sizes:
        font = get_font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= max_width and h <= max_height:
            return font, text, w, h

    # Smallest font still doesn't fit — truncate with ellipsis
    font = get_font(font_sizes[-1], bold=bold)
    for end in range(len(text) - 1, 0, -1):
        truncated = text[:end] + "\u2026"
        bbox = draw.textbbox((0, 0), truncated, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= max_width:
            return font, truncated, w, h

    # Edge case: even single char + ellipsis doesn't fit
    return font, "\u2026", 0, 0


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: tuple[int, int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Draw text centered within a bounding box."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x + (w - tw) // 2
    ty = y + (h - th) // 2
    draw.text((tx, ty), text, fill=fill, font=font)
