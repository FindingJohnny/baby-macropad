"""Button icon rendering for the M18 full-screen LCD.

The M18's 15 screen keys are one 480x272 LCD panel. We compose all key
icons into a single 480x272 background image using the same Tabler icons
from the iOS app, tinted with category colors.

Grid layout: 5 columns x 3 rows = 15 keys.
Full cell: 96x~91 pixels, but physical button bezels obscure the edges.
Visible area per button: ~72x60 pixels (measured via calibration patterns).
Content is centered within the visible area, not the full cell.
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

# Visible area per button — measured via calibration patterns.
# The physical bezels obscure ~12px on each side horizontally and
# ~15-20px on each side vertically. These are the pixel rectangles
# actually visible through the button cutouts.
#
# Columns (X ranges): C0=11-83, C1=107-179, C2=203-275, C3=299-371, C4=395-467
# Rows (Y ranges):    R0=10-70,  R1=110-170, R2=200-270
VIS_COL_X = [11, 107, 203, 299, 395]  # Left edge of visible area per column
VIS_COL_W = [72, 72, 72, 72, 72]      # Visible width per column
VIS_ROW_Y = [10, 110, 200]            # Top edge of visible area per row
VIS_ROW_H = [60, 60, 70]              # Visible height per row

BG_COLOR = (28, 28, 30)  # Near-black, matches iOS bbBackground dark

# Icon asset directory (relative to package root)
_ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "assets" / "icons"

# Category colors (same as iOS design system)
ICON_COLORS = {
    "breast_left": (102, 204, 102),   # Soft green
    "breast_right": (102, 204, 102),
    "bottle": (102, 204, 102),
    "pump": (102, 204, 102),
    "diaper_pee": (204, 170, 68),     # Warm amber
    "diaper_poop": (204, 170, 68),
    "diaper_both": (204, 170, 68),
    "sleep": (102, 153, 204),         # Soft blue
    "note": (153, 153, 153),          # Warm gray
    "settings": (200, 200, 200),      # Neutral gray
    "light": (255, 204, 0),           # Yellow
    "fan": (0, 204, 204),             # Cyan
    "sound": (180, 180, 180),         # Light gray
    "scene_off": (255, 255, 255),     # White
}

# Map icon names to PNG asset files (same Tabler icons as iOS app).
# String values map to a single asset file. Tuple values trigger composite
# rendering via _load_two_icon_composite (first icon top-left, second bottom-right).
ICON_ASSETS: dict[str, str | tuple[str, str]] = {
    "breast_left": "breast",
    "breast_right": "breast",
    "bottle": "bottle",
    "pump": "pump",
    "diaper_pee": "diaper",
    "diaper_poop": "poo",
    "diaper_both": ("poo", "diaper"),
    "sleep": "moon",
    "note": "note",
    "settings": "gear",
}

# Labels shown below the icon
ICON_LABELS = {
    "breast_left": "LEFT",
    "breast_right": "RIGHT",
    "bottle": "BOTTLE",
    "pump": "PUMP",
    "diaper_pee": "PEE",
    "diaper_poop": "POOP",
    "diaper_both": "BOTH",
    "sleep": "SLEEP",
    "note": "NOTE",
    "settings": "SETTINGS",
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


def _load_two_icon_composite(
    asset_a: str,
    asset_b: str,
    color: tuple[int, int, int],
    size: int,
) -> Image.Image | None:
    """Render two icons as a 2x2 quadrant composite (a top-left, b bottom-right)."""
    half = size // 2
    a = _load_and_tint(asset_a, color, half)
    b = _load_and_tint(asset_b, color, half)
    if a is None or b is None:
        return None
    composite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    composite.paste(a, (0, 0), a)
    composite.paste(b, (half, half), b)
    return composite


def render_key_grid(
    buttons: dict[int, Any],
    runtime_state: dict[int, str] | None = None,
) -> Image.Image:
    """Render all button icons as a single 480x272 composite image.

    Content is centered within the measured visible area of each button,
    not the full cell. The bezels hide ~12px per side horizontally and
    ~15-20px per side vertically, so we render into the ~72x60px window
    that's actually visible through each physical button cutout.

    Args:
        buttons: Key number (1-15) to button config dict/object.
        runtime_state: Optional key number to state string mapping.
            - Sleep (key 13): "active" swaps icon to sunrise + "WAKE UP" label
              with elapsed time from state value (e.g. "active:1h 32m").
            - Breast (keys 11, 6): "suggested" adds a "NEXT" badge.
    """
    runtime_state = runtime_state or {}

    screen = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(screen)
    label_font = _get_font(11)
    fallback_font = _get_font(18)
    badge_font = _get_font(8)

    icon_size = 36  # Sized to fit within 60px visible height with label
    label_height = 13
    icon_label_gap = 3
    content_height = icon_size + icon_label_gap + label_height  # ~52px

    for key_num, button in buttons.items():
        pos = _key_position(key_num)
        if pos is None:
            continue

        col, row = pos

        # Visible area for this button (measured via calibration)
        vx = VIS_COL_X[col]
        vy = VIS_ROW_Y[row]
        vw = VIS_COL_W[col]
        vh = VIS_ROW_H[row]

        icon_name = button.icon if hasattr(button, "icon") else button.get("icon", "")
        label = button.label if hasattr(button, "label") else button.get("label", "?")
        color = ICON_COLORS.get(icon_name, (200, 200, 200))

        state = runtime_state.get(key_num, "idle")
        is_sleep_active = icon_name == "sleep" and state.startswith("active")
        is_suggested = state == "suggested"

        # Brighter card background when suggested
        card_bg_factor = 0.18 if is_suggested else 0.12
        margin = 2
        draw.rounded_rectangle(
            [vx + margin, vy + margin, vx + vw - margin, vy + vh - margin],
            radius=5,
            fill=_darken(color, card_bg_factor),
        )

        # Determine asset and label overrides for active sleep
        if is_sleep_active:
            active_asset = "sunrise"
            active_label = "WAKE UP"
            # Extract elapsed time if provided as "active:1h 32m"
            elapsed = state.split(":", 1)[1] if ":" in state else None
            # Use smaller icon to fit label + elapsed time
            active_icon_size = 26
            active_label_font = _get_font(10)
            elapsed_font = _get_font(9)

            tinted = _load_and_tint(active_asset, color, active_icon_size)
            if tinted:
                # Custom layout: icon + WAKE UP + elapsed, all vertically stacked
                total_h = active_icon_size + 2 + 11  # icon + gap + label
                if elapsed:
                    total_h += 1 + 10  # gap + elapsed line
                top_y = vy + (vh - total_h) // 2

                ix = vx + (vw - active_icon_size) // 2
                screen.paste(tinted, (ix, top_y), tinted)

                bbox = draw.textbbox((0, 0), active_label, font=active_label_font)
                lw = bbox[2] - bbox[0]
                lx = vx + (vw - lw) // 2
                ly = top_y + active_icon_size + 2
                draw.text((lx, ly), active_label, fill=color, font=active_label_font)

                if elapsed:
                    bbox = draw.textbbox((0, 0), elapsed, font=elapsed_font)
                    ew = bbox[2] - bbox[0]
                    ex = vx + (vw - ew) // 2
                    ey = ly + 11 + 1
                    draw.text((ex, ey), elapsed, fill=color, font=elapsed_font)
            continue

        # Vertically center icon+label as a group within the visible area
        top_offset = (vh - content_height) // 2

        # Try to load and draw the Tabler icon
        asset = ICON_ASSETS.get(icon_name)
        icon_drawn = False
        if isinstance(asset, tuple):
            # Composite icon (e.g. diaper_both = poo + diaper)
            tinted = _load_two_icon_composite(asset[0], asset[1], color, icon_size)
            if tinted:
                ix = vx + (vw - icon_size) // 2
                iy = vy + top_offset
                screen.paste(tinted, (ix, iy), tinted)
                icon_drawn = True
        elif asset:
            tinted = _load_and_tint(asset, color, icon_size)
            if tinted:
                ix = vx + (vw - icon_size) // 2
                iy = vy + top_offset
                screen.paste(tinted, (ix, iy), tinted)
                icon_drawn = True

        if not icon_drawn:
            # Fallback: draw text centered in the icon area
            text = label[:4].upper()
            bbox = draw.textbbox((0, 0), text, font=fallback_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = vx + (vw - tw) // 2
            ty = vy + top_offset + (icon_size - th) // 2
            draw.text((tx, ty), text, fill=color, font=fallback_font)

        # Draw label below icon
        display_label = ICON_LABELS.get(icon_name, label[:6].upper())
        bbox = draw.textbbox((0, 0), display_label, font=label_font)
        lw = bbox[2] - bbox[0]
        lx = vx + (vw - lw) // 2
        ly = vy + top_offset + icon_size + icon_label_gap
        draw.text((lx, ly), display_label, fill=color, font=label_font)

        # Draw "NEXT" badge for suggested breast buttons
        if is_suggested and icon_name in ("breast_left", "breast_right"):
            badge_text = "\u25b6 NEXT"
            bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
            bw = bbox[2] - bbox[0]
            bx = vx + (vw - bw) // 2
            by = ly + label_height + 1
            draw.text((bx, by), badge_text, fill=color, font=badge_font)

    return screen


def save_key_grid(
    buttons: dict[int, Any],
    output_path: Path,
    runtime_state: dict[int, str] | None = None,
) -> Path:
    """Render and save the key grid image as JPEG."""
    img = render_key_grid(buttons, runtime_state=runtime_state)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=90)
    logger.info("Saved key grid to %s", output_path)
    return output_path


def get_key_grid_bytes(
    buttons: dict[int, Any],
    runtime_state: dict[int, str] | None = None,
) -> bytes:
    """Render the key grid and return as JPEG bytes."""
    img = render_key_grid(buttons, runtime_state=runtime_state)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
