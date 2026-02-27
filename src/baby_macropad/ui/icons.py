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

# --- Framework imports (canonical sources) ---
from .framework.icon_cache import load_and_tint as _load_and_tint
from .framework.icon_cache import load_composite as _load_two_icon_composite
from .framework.primitives import (
    BACK_BUTTON_BG,
    BG_COLOR,
    CARD_MARGIN,
    CARD_RADIUS,
    CELL_W,
    COLS,
    ICON_ASSETS,
    ICON_COLORS,
    ICON_LABELS,
    ROWS,
    SCREEN_H,
    SCREEN_W,
    SECONDARY_TEXT,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    darken as _darken,
    key_to_grid,
)
from .framework.text_engine import get_font

logger = logging.getLogger(__name__)


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a bold font at the given size. Delegates to text_engine.get_font."""
    return get_font(size, bold=True)


def _key_position(key_num: int) -> tuple[int, int] | None:
    """Key number (1-15) to grid (col, row). Delegates to primitives.key_to_grid."""
    return key_to_grid(key_num)


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
