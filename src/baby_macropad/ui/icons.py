"""64x64 button icon generation using Pillow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

ICON_SIZE = (64, 64)
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

# Unicode symbols for visual distinctiveness
ICON_SYMBOLS = {
    "breast_left": "\u2190",   # left arrow
    "breast_right": "\u2192",  # right arrow
    "bottle": "\U0001f37c",    # baby bottle emoji
    "diaper_pee": "\U0001f4a7", # droplet
    "diaper_poop": "\U0001f4a9", # poop emoji
    "diaper_both": "\u2194",   # left-right arrow
    "sleep": "\u263e",         # moon
    "note": "\u270e",          # pencil
    "light": "\u2600",         # sun
    "fan": "\u2731",           # heavy asterisk
    "sound": "\u266b",         # music notes
    "scene_off": "\u2716",     # heavy X
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


def generate_icon(icon_name: str, label: str | None = None) -> Image.Image:
    """Generate a 64x64 button icon with text label.

    Args:
        icon_name: Key into ICON_COLORS/ICON_LABELS (e.g. "breast_left")
        label: Override the default label text

    Returns:
        PIL Image object (64x64, RGB)
    """
    img = Image.new("RGB", ICON_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(img)

    color = ICON_COLORS.get(icon_name, (200, 200, 200))
    text = label or ICON_LABELS.get(icon_name, "?")

    # Draw large centered text
    font = _get_font(22)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (ICON_SIZE[0] - text_w) // 2
    y = (ICON_SIZE[1] - text_h) // 2
    draw.text((x, y), text, fill=color, font=font)

    return img


def generate_all_icons(buttons: dict[int, Any], output_dir: Path) -> dict[int, Path]:
    """Generate icon images for all configured buttons.

    Args:
        buttons: Dict mapping key number to ButtonConfig-like objects
        output_dir: Directory to save generated JPEG icons

    Returns:
        Dict mapping key number to icon file path
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    icon_paths: dict[int, Path] = {}

    for key_num, button in buttons.items():
        icon_name = button.icon if hasattr(button, "icon") else button.get("icon", "")
        label_text = button.label if hasattr(button, "label") else button.get("label", "")

        if not icon_name:
            continue

        img = generate_icon(icon_name, label=None)
        path = output_dir / f"key_{key_num}.jpg"
        img.save(path, "JPEG", quality=90)
        icon_paths[key_num] = path
        logger.debug("Generated icon for key %d: %s", key_num, path)

    return icon_paths
