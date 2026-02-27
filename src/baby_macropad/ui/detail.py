"""Detail screen renderer for parameter selection before logging.

Shows a title, countdown timer, selectable option cards in the top row,
and a BACK button in the bottom-left. Used for breast side, bottle source,
poop consistency, etc.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageDraw

from .icons import BG_COLOR, SCREEN_H, SCREEN_W, VIS_COL_W, VIS_COL_X, VIS_ROW_H, VIS_ROW_Y, _get_font

logger = logging.getLogger(__name__)

# Card styling
_CARD_RADIUS = 6
_CARD_MARGIN = 2
_SECONDARY_TEXT = (142, 142, 147)


def _draw_card(
    draw: ImageDraw.ImageDraw,
    col: int,
    row: int,
    fill: tuple[int, int, int] | None,
    outline: tuple[int, int, int] | None,
) -> tuple[int, int, int, int]:
    """Draw a rounded rect card in the given grid cell. Returns the bounding box."""
    x = VIS_COL_X[col] + _CARD_MARGIN
    y = VIS_ROW_Y[row] + _CARD_MARGIN
    w = VIS_COL_W[col] - _CARD_MARGIN * 2
    h = VIS_ROW_H[row] - _CARD_MARGIN * 2
    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=_CARD_RADIUS,
        fill=fill,
        outline=outline,
        width=2 if outline else 0,
    )
    return (x, y, x + w, y + h)


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    bbox: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    font,
) -> None:
    """Draw text centered within the given bounding box."""
    tb = draw.textbbox((0, 0), text, font=font)
    tw = tb[2] - tb[0]
    th = tb[3] - tb[1]
    tx = bbox[0] + (bbox[2] - bbox[0] - tw) // 2
    ty = bbox[1] + (bbox[3] - bbox[1] - th) // 2
    draw.text((tx, ty), text, fill=fill, font=font)


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def render_detail_screen(
    title: str,
    options: list[dict],
    timer_seconds: int,
    category_color: tuple[int, int, int],
) -> bytes:
    """Render a detail/parameter selection screen.

    Args:
        title: Screen title, e.g. "LEFT BREAST", "POOP"
        options: List of dicts with keys: label, key_num, selected (bool)
        timer_seconds: Countdown timer remaining seconds
        category_color: RGB tuple for the category accent color

    Returns:
        JPEG image bytes (480x272)
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = _get_font(16)
    option_font = _get_font(12)
    timer_font = _get_font(14)
    back_font = _get_font(12)

    # Title — centered in middle row (spans columns 1-3)
    tb = draw.textbbox((0, 0), title, font=title_font)
    tw = tb[2] - tb[0]
    center_x = (VIS_COL_X[1] + VIS_COL_X[3] + VIS_COL_W[3]) // 2
    ty = VIS_ROW_Y[1] + (VIS_ROW_H[1] - (tb[3] - tb[1])) // 2
    draw.text((center_x - tw // 2, ty), title, fill=(255, 255, 255), font=title_font)

    # Timer countdown — middle-right (key 10 area = col 4, row 1)
    timer_text = f"{timer_seconds}s"
    timer_box = _draw_card(draw, 4, 1, fill=_darken(category_color, 0.15), outline=None)
    _draw_centered_text(draw, timer_text, timer_box, category_color, timer_font)

    # Option cards — top row (keys 11-14 = row 0, cols 0-3)
    for opt in options:
        key_num = opt.get("key_num", 11)
        col = key_num - 11
        if col < 0 or col > 3:
            continue

        selected = opt.get("selected", False)
        label = opt.get("label", "?")

        if selected:
            card_box = _draw_card(draw, col, 0, fill=category_color, outline=None)
            _draw_centered_text(draw, label, card_box, (255, 255, 255), option_font)
        else:
            card_box = _draw_card(draw, col, 0, fill=_darken(category_color, 0.1), outline=category_color)
            _draw_centered_text(draw, label, card_box, category_color, option_font)

    # BACK button — bottom-left (key 1 = col 0, row 2)
    back_box = _draw_card(draw, 0, 2, fill=(38, 38, 40), outline=None)
    _draw_centered_text(draw, "BACK", back_box, _SECONDARY_TEXT, back_font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
