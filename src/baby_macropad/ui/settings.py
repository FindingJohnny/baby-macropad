"""Settings screen renderer.

Shows configurable settings as labeled cards:
  - Timer duration (cycle through values)
  - Celebration style
  - Skip breast detail toggle
  - BACK button at key 1
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageDraw

from .icons import (
    BACK_BUTTON_BG,
    BG_COLOR,
    CARD_MARGIN,
    CARD_RADIUS,
    ICON_COLORS,
    SCREEN_H,
    SCREEN_W,
    SECONDARY_TEXT,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    _get_font,
)

logger = logging.getLogger(__name__)

_SETTINGS_COLOR = ICON_COLORS.get("settings", (200, 200, 200))


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def _draw_card(
    draw: ImageDraw.ImageDraw,
    col: int,
    row: int,
    fill: tuple[int, int, int] | None,
    outline: tuple[int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    x = VIS_COL_X[col] + CARD_MARGIN
    y = VIS_ROW_Y[row] + CARD_MARGIN
    w = VIS_COL_W[col] - CARD_MARGIN * 2
    h = VIS_ROW_H[row] - CARD_MARGIN * 2
    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=CARD_RADIUS,
        fill=fill,
        outline=outline,
        width=2 if outline else 0,
    )
    return (x, y, x + w, y + h)


def _draw_two_line(
    draw: ImageDraw.ImageDraw,
    line1: str,
    line2: str,
    bbox: tuple[int, int, int, int],
    color1: tuple[int, int, int],
    color2: tuple[int, int, int],
    font1,
    font2,
) -> None:
    """Draw two lines of text centered in a bounding box."""
    tb1 = draw.textbbox((0, 0), line1, font=font1)
    tb2 = draw.textbbox((0, 0), line2, font=font2)
    h1 = tb1[3] - tb1[1]
    h2 = tb2[3] - tb2[1]
    gap = 3
    total_h = h1 + gap + h2
    bx = bbox[0]
    bw = bbox[2] - bbox[0]
    by = bbox[1] + (bbox[3] - bbox[1] - total_h) // 2

    w1 = tb1[2] - tb1[0]
    draw.text((bx + (bw - w1) // 2, by), line1, fill=color1, font=font1)
    w2 = tb2[2] - tb2[0]
    draw.text((bx + (bw - w2) // 2, by + h1 + gap), line2, fill=color2, font=font2)


def render_settings_screen(
    timer_seconds: int = 7,
    celebration_style: str = "color_fill",
    skip_breast_detail: bool = False,
) -> bytes:
    """Render the settings screen.

    Args:
        timer_seconds: Current auto-commit timer value
        celebration_style: Current celebration animation style
        skip_breast_detail: Whether breast detail screen is skipped

    Returns:
        JPEG image bytes (480x272)
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    label_font = _get_font(9)
    value_font = _get_font(14)
    title_font = _get_font(14)
    back_font = _get_font(12)

    # Title — "SETTINGS" centered in middle-center area
    title = "SETTINGS"
    tb = draw.textbbox((0, 0), title, font=title_font)
    tw = tb[2] - tb[0]
    tx = (SCREEN_W - tw) // 2
    ty = VIS_ROW_Y[1] + (VIS_ROW_H[1] - (tb[3] - tb[1])) // 2
    draw.text((tx, ty), title, fill=_SETTINGS_COLOR, font=title_font)

    # Setting cards in top row
    # Key 11 (col 0): Timer duration
    card = _draw_card(draw, 0, 0, fill=_darken(_SETTINGS_COLOR, 0.12), outline=_darken(_SETTINGS_COLOR, 0.3))
    _draw_two_line(draw, "Timer", f"{timer_seconds}s", card, SECONDARY_TEXT, _SETTINGS_COLOR, label_font, value_font)

    # Key 12 (col 1): Celebration style
    style_short = {
        "color_fill": "Fill",
        "radiate": "Glow",
        "randomize": "Fun",
        "none": "Off",
    }.get(celebration_style, celebration_style[:4])
    card = _draw_card(draw, 1, 0, fill=_darken(_SETTINGS_COLOR, 0.12), outline=_darken(_SETTINGS_COLOR, 0.3))
    _draw_two_line(draw, "Celeb", style_short, card, SECONDARY_TEXT, _SETTINGS_COLOR, label_font, value_font)

    # Key 13 (col 2): Skip breast detail
    skip_text = "ON" if skip_breast_detail else "OFF"
    card = _draw_card(draw, 2, 0, fill=_darken(_SETTINGS_COLOR, 0.12), outline=_darken(_SETTINGS_COLOR, 0.3))
    _draw_two_line(draw, "Quick", skip_text, card, SECONDARY_TEXT, _SETTINGS_COLOR, label_font, value_font)

    # BACK button — key 1 = col 0, row 2
    back_box = _draw_card(draw, 0, 2, fill=BACK_BUTTON_BG)
    tb = draw.textbbox((0, 0), "BACK", font=back_font)
    tw = tb[2] - tb[0]
    th = tb[3] - tb[1]
    bx = back_box[0] + (back_box[2] - back_box[0] - tw) // 2
    by = back_box[1] + (back_box[3] - back_box[1] - th) // 2
    draw.text((bx, by), "BACK", fill=SECONDARY_TEXT, font=back_font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
