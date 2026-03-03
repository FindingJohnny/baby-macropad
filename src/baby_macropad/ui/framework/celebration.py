"""Celebration animation renderer — draws directly on the 480x272 canvas.

Each style returns a list of JPEG bytes (frames). The bezels between
button cutouts naturally "window" each cell's portion of the full-canvas
drawing, creating organic visual effects from simple PIL operations.

Design constraints (Pi Zero W):
  - ~50ms USB transfer per frame + ~50-150ms PIL render = 5-10 fps
  - Keep to 1-3 frames max for snappy feel
  - Simple PIL ops: filled shapes, gradients, lines — no filters
"""

from __future__ import annotations

import io
import math
import random

from PIL import Image, ImageDraw

from .icon_cache import load_and_tint
from .primitives import (
    BG_COLOR,
    SCREEN_H,
    SCREEN_W,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
)

# Canvas center
_CX = SCREEN_W // 2  # 240
_CY = SCREEN_H // 2  # 136


def _lighten(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Blend color toward white by factor (0.0 = unchanged, 1.0 = white)."""
    r, g, b = color
    return (
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )


def _to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _paste_checkmark(img: Image.Image, cx: int, cy: int, size: int = 36) -> None:
    """Composite the white checkmark icon at a given center position."""
    icon = load_and_tint("check", (255, 255, 255), size)
    if icon:
        img.paste(icon, (cx - size // 2, cy - size // 2), icon)


def _cell_centers() -> list[tuple[int, int]]:
    """Return (cx, cy) for all 15 visible cell centers."""
    centers = []
    for row in range(3):
        for col in range(5):
            cx = VIS_COL_X[col] + VIS_COL_W[col] // 2
            cy = VIS_ROW_Y[row] + VIS_ROW_H[row] // 2
            centers.append((cx, cy))
    return centers


def _draw_radial_glow(
    img: Image.Image,
    color: tuple[int, int, int],
    cx: int, cy: int,
    radius: int,
    rings: int = 20,
) -> None:
    """Draw a radial gradient glow using concentric filled ellipses.

    Outer rings are dimmer, inner rings are brighter (closer to white).
    Fast enough on Pi Zero: ~20 ellipse draws on a 480x272 image.
    """
    draw = ImageDraw.Draw(img)
    for i in range(rings, 0, -1):
        t = i / rings  # 1.0 = outermost, approaching 0.0 = center
        r = int(radius * t)
        # Lighten more toward center
        brightness = 1.0 - t  # 0.0 at edge, 1.0 at center
        ring_color = _lighten(color, brightness * 0.6)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=ring_color,
        )


def _render_flash(color: tuple[int, int, int]) -> list[bytes]:
    """1 frame: Radial glow from canvas center + checkmark.

    A warm, organic glow that fades from bright-white center to
    category color at the edges. Viewed through the bezel grid,
    center cells appear brightest, edge cells are dimmer category color.
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), color)
    # Overlay a bright radial glow at center
    _draw_radial_glow(img, color, _CX, _CY, radius=280, rings=25)
    _paste_checkmark(img, _CX, _CY)
    return [_to_jpeg(img)]


def _render_starburst(color: tuple[int, int, int]) -> list[bytes]:
    """2 frames: Radiating lines from center, then full radial glow.

    Frame 1: Dark background with bright lines shooting outward from
    canvas center in the category color. Through the bezel grid, each
    cell shows line segments at different angles — a sunburst effect.

    Frame 2: Full radial glow (same as flash).
    """
    # Frame 1: Starburst lines on dark bg
    img1 = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw1 = ImageDraw.Draw(img1)
    bright = _lighten(color, 0.4)
    num_rays = 24
    ray_length = 350  # extends past screen edges
    for i in range(num_rays):
        angle = 2 * math.pi * i / num_rays
        ex = int(_CX + ray_length * math.cos(angle))
        ey = int(_CY + ray_length * math.sin(angle))
        draw1.line([(_CX, _CY), (ex, ey)], fill=bright, width=3)
    # Bright center dot
    draw1.ellipse([_CX - 15, _CY - 15, _CX + 15, _CY + 15], fill=_lighten(color, 0.7))
    _paste_checkmark(img1, _CX, _CY)

    # Frame 2: Full glow
    img2 = Image.new("RGB", (SCREEN_W, SCREEN_H), color)
    _draw_radial_glow(img2, color, _CX, _CY, radius=280, rings=25)
    _paste_checkmark(img2, _CX, _CY)

    return [_to_jpeg(img1), _to_jpeg(img2)]


def _render_sparkle(color: tuple[int, int, int]) -> list[bytes]:
    """2 frames: Scattered bright circles alternating positions.

    Each frame has 8-10 circles of varying sizes (6-18px radius)
    placed within visible cell areas. Frames use complementary
    positions so the eye perceives twinkling/motion.
    """
    rng = random.Random(42)  # deterministic for consistency
    cells = _cell_centers()

    def _make_sparkle_frame(seed_offset: int) -> bytes:
        rng_frame = random.Random(42 + seed_offset)
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
        draw = ImageDraw.Draw(img)
        # Pick 8 cells to light up
        selected = rng_frame.sample(range(len(cells)), min(8, len(cells)))
        for idx in selected:
            cx, cy = cells[idx]
            # Jitter position within the cell
            cx += rng_frame.randint(-20, 20)
            cy += rng_frame.randint(-15, 15)
            r = rng_frame.randint(6, 18)
            brightness = rng_frame.uniform(0.3, 0.8)
            circle_color = _lighten(color, brightness)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=circle_color)
        # Small center checkmark
        _paste_checkmark(img, _CX, _CY, size=28)
        return _to_jpeg(img)

    return [_make_sparkle_frame(0), _make_sparkle_frame(100)]


def _render_spotlight(color: tuple[int, int, int]) -> list[bytes]:
    """2 frames: Tight center spotlight expanding outward.

    Frame 1: Small bright circle at canvas center, rest dark.
    Only the center ~3 cells are lit. Creates a "focusing" feel.

    Frame 2: Expanded glow filling most of the grid.
    """
    # Frame 1: Tight spotlight
    img1 = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    _draw_radial_glow(img1, color, _CX, _CY, radius=120, rings=15)
    _paste_checkmark(img1, _CX, _CY)

    # Frame 2: Expanded glow
    img2 = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    _draw_radial_glow(img2, color, _CX, _CY, radius=320, rings=25)
    _paste_checkmark(img2, _CX, _CY)

    return [_to_jpeg(img1), _to_jpeg(img2)]


# Style registry
_STYLES: dict[str, any] = {
    "flash": _render_flash,
    "starburst": _render_starburst,
    "sparkle": _render_sparkle,
    "spotlight": _render_spotlight,
}


def render_celebration_frames(
    category_color: tuple[int, int, int], style: str,
) -> list[bytes]:
    """Public API: render celebration frames for a given style."""
    renderer = _STYLES.get(style)
    if renderer is None:
        return []
    return renderer(category_color)
