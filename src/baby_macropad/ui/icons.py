"""Button icon rendering for the M18 full-screen LCD.

The M18's 15 screen keys are one 480x272 LCD panel. Individual key image
commands don't work on our hardware variant (VID 0x5548). Instead, we
compose all key icons into a single 480x272 background image and send
it via set_background_image_stream.

Grid layout: 5 columns x 3 rows = 15 keys.
Each cell: 96x90 pixels.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# M18 screen dimensions
SCREEN_W = 480
SCREEN_H = 272
COLS = 5
ROWS = 3
CELL_W = SCREEN_W // COLS  # 96
CELL_H = SCREEN_H // ROWS  # 90

BG_COLOR = (28, 28, 30)  # Near-black, matches iOS bbBackground dark

# Category colors from the UX design doc
ICON_COLORS = {
    "breast_left": (102, 204, 102),   # Soft green
    "breast_right": (102, 204, 102),
    "bottle": (102, 204, 102),
    "diaper_pee": (204, 170, 68),     # Warm amber
    "diaper_poop": (204, 170, 68),
    "diaper_both": (204, 170, 68),
    "sleep": (102, 153, 204),         # Soft blue
    "note": (153, 153, 153),          # Warm gray
    "light": (255, 204, 0),           # Yellow
    "fan": (0, 204, 204),             # Cyan
    "sound": (180, 180, 180),         # Light gray
    "scene_off": (255, 255, 255),     # White
}

# Short text labels for each icon
ICON_LABELS = {
    "breast_left": "L",
    "breast_right": "R",
    "bottle": "BTL",
    "diaper_pee": "PEE",
    "diaper_poop": "POO",
    "diaper_both": "P+P",
    "sleep": "ZZZ",
    "note": "NOTE",
    "light": "LGT",
    "fan": "FAN",
    "sound": "SND",
    "scene_off": "OFF",
}


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load DejaVu Sans Bold, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/System/Library/Fonts/Helvetica.ttc",                     # macOS
    ]
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _key_position(key_num: int) -> tuple[int, int] | None:
    """Convert key number (1-15) to grid position (col, row).

    Key layout on M18 (5x3 grid):
      Row 0:  1  2  3  4  5
      Row 1:  6  7  8  9 10
      Row 2: 11 12 13 14 15
    """
    if key_num < 1 or key_num > 15:
        return None
    idx = key_num - 1
    col = idx % COLS
    row = idx // COLS
    return (col, row)


def render_key_grid(buttons: dict[int, Any]) -> Image.Image:
    """Render all button icons as a single 480x272 composite image.

    Args:
        buttons: Dict mapping key number (1-15) to ButtonConfig objects

    Returns:
        PIL Image (480x272, RGB) ready for set_background_image_stream
    """
    screen = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(screen)
    font = _get_font(22)

    for key_num, button in buttons.items():
        pos = _key_position(key_num)
        if pos is None:
            continue

        col, row = pos
        x = col * CELL_W
        y = row * CELL_H

        icon_name = button.icon if hasattr(button, "icon") else button.get("icon", "")
        label = button.label if hasattr(button, "label") else button.get("label", "?")

        color = ICON_COLORS.get(icon_name, (200, 200, 200))
        text = ICON_LABELS.get(icon_name, label[:4])

        # Draw colored rounded-ish rectangle with margin
        margin = 4
        draw.rectangle(
            [x + margin, y + margin, x + CELL_W - margin, y + CELL_H - margin],
            fill=_darken(color, 0.3),
        )

        # Draw text centered in cell
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x + (CELL_W - tw) // 2
        ty = y + (CELL_H - th) // 2
        draw.text((tx, ty), text, fill=color, font=font)

    return screen


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Darken an RGB color by a factor (0=black, 1=original)."""
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def save_key_grid(buttons: dict[int, Any], output_path: Path) -> Path:
    """Render and save the key grid image as JPEG."""
    img = render_key_grid(buttons)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=90)
    logger.info("Saved key grid to %s", output_path)
    return output_path


def get_key_grid_bytes(buttons: dict[int, Any]) -> bytes:
    """Render the key grid and return as JPEG bytes."""
    img = render_key_grid(buttons)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
