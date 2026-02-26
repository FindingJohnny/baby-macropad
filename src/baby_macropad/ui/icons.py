"""Button icon rendering for the M18 full-screen LCD.

The M18's 15 screen keys are one 480x272 LCD panel. We compose all key
icons into a single 480x272 background image using the same Tabler icons
from the iOS app, tinted with category colors.

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

# Icon asset directory (relative to package root)
_ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "assets" / "icons"

# Category colors (same as iOS design system)
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

# Map icon names to PNG asset files (same Tabler icons as iOS app)
ICON_ASSETS = {
    "breast_left": "bottle",
    "breast_right": "bottle",
    "bottle": "bottle",
    "diaper_pee": "diaper",
    "diaper_poop": "poo",
    "diaper_both": "diaper",
    "sleep": "moon",
    "note": "note",
}

# Labels shown below the icon
ICON_LABELS = {
    "breast_left": "LEFT",
    "breast_right": "RIGHT",
    "bottle": "BOTTLE",
    "diaper_pee": "PEE",
    "diaper_poop": "POOP",
    "diaper_both": "BOTH",
    "sleep": "SLEEP",
    "note": "NOTE",
    "light": "LIGHT",
    "fan": "FAN",
    "sound": "SOUND",
    "scene_off": "OFF",
}

# Cache loaded + tinted icons
_icon_cache: dict[str, Image.Image] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _key_position(key_num: int) -> tuple[int, int] | None:
    """Key number (1-15) to grid (col, row).

    M18 physical-to-key mapping (verified by testing):
      Top row:    KEY_11  KEY_12  KEY_13  KEY_14  KEY_15
      Middle row: KEY_6   KEY_7   KEY_8   KEY_9   KEY_10
      Bottom row: KEY_1   KEY_2   KEY_3   KEY_4   KEY_5

    Top and bottom rows are swapped vs naive numbering.
    """
    if key_num < 1 or key_num > 15:
        return None
    # Map key number to physical grid position
    if 1 <= key_num <= 5:
        # Keys 1-5 are on the BOTTOM row (row 2)
        return (key_num - 1, 2)
    elif 6 <= key_num <= 10:
        # Keys 6-10 are in the MIDDLE row (row 1)
        return (key_num - 6, 1)
    else:
        # Keys 11-15 are on the TOP row (row 0)
        return (key_num - 11, 0)


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def _load_and_tint(asset_name: str, color: tuple[int, int, int], size: int) -> Image.Image | None:
    """Load a white PNG icon, tint it with the given color, and resize."""
    cache_key = f"{asset_name}_{color}_{size}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    png_path = _ASSETS_DIR / f"{asset_name}.png"
    if not png_path.exists():
        logger.warning("Icon asset not found: %s", png_path)
        return None

    # Load white icon with alpha
    icon = Image.open(png_path).convert("RGBA")
    icon = icon.resize((size, size), Image.LANCZOS)

    # Tint: multiply white pixels by color, preserving alpha
    r, g, b = color
    pixels = icon.load()
    for y in range(icon.height):
        for x in range(icon.width):
            pr, pg, pb, pa = pixels[x, y]
            if pa > 0:
                # Scale the white pixel by the target color
                pixels[x, y] = (
                    pr * r // 255,
                    pg * g // 255,
                    pb * b // 255,
                    pa,
                )

    _icon_cache[cache_key] = icon
    return icon


def render_key_grid(buttons: dict[int, Any]) -> Image.Image:
    """Render all button icons as a single 480x272 composite image."""
    screen = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(screen)
    label_font = _get_font(11)
    fallback_font = _get_font(20)

    icon_size = 40  # Icon render size in pixels

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

        # Draw subtle background card
        margin = 3
        draw.rounded_rectangle(
            [x + margin, y + margin, x + CELL_W - margin, y + CELL_H - margin],
            radius=6,
            fill=_darken(color, 0.12),
        )

        # Try to load and draw the Tabler icon
        asset_name = ICON_ASSETS.get(icon_name)
        icon_drawn = False
        if asset_name:
            tinted = _load_and_tint(asset_name, color, icon_size)
            if tinted:
                # Center icon in upper 2/3 of cell
                ix = x + (CELL_W - icon_size) // 2
                iy = y + (CELL_H - icon_size) // 2 - 10
                screen.paste(tinted, (ix, iy), tinted)  # Use alpha mask
                icon_drawn = True

        if not icon_drawn:
            # Fallback: draw text
            text = label[:4].upper()
            bbox = draw.textbbox((0, 0), text, font=fallback_font)
            tw = bbox[2] - bbox[0]
            tx = x + (CELL_W - tw) // 2
            ty = y + (CELL_H - 20) // 2 - 10
            draw.text((tx, ty), text, fill=color, font=fallback_font)

        # Draw label below icon
        display_label = ICON_LABELS.get(icon_name, label[:6].upper())
        bbox = draw.textbbox((0, 0), display_label, font=label_font)
        lw = bbox[2] - bbox[0]
        lx = x + (CELL_W - lw) // 2
        ly = y + CELL_H - 16
        draw.text((lx, ly), display_label, fill=color, font=label_font)

    return screen


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
