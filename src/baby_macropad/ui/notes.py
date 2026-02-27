"""Notes submenu renderer — category selection grid.

Shows available note categories as selectable cards in the top and
middle rows, with a BACK button always at key 1 (bottom-left).
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
    ICON_ASSETS,
    ICON_COLORS,
    SCREEN_H,
    SCREEN_W,
    SECONDARY_TEXT,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    _get_font,
    _load_and_tint,
)

logger = logging.getLogger(__name__)

_NOTES_COLOR = ICON_COLORS.get("note", (153, 153, 153))


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def _draw_card(
    draw: ImageDraw.ImageDraw,
    col: int,
    row: int,
    fill: tuple[int, int, int] | None,
    outline: tuple[int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Draw a rounded rect card in the given grid cell. Returns bounding box."""
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


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    bbox: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    font,
) -> None:
    tb = draw.textbbox((0, 0), text, font=font)
    tw = tb[2] - tb[0]
    th = tb[3] - tb[1]
    tx = bbox[0] + (bbox[2] - bbox[0] - tw) // 2
    ty = bbox[1] + (bbox[3] - bbox[1] - th) // 2
    draw.text((tx, ty), text, fill=fill, font=font)


# Key layout: top row first (11-15), middle row (6-10), bottom row (2-5)
# Key 1 reserved for BACK
_OPTION_KEYS = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 2, 3, 4, 5]


def _key_to_grid(key_num: int) -> tuple[int, int] | None:
    """Map key number to (col, row)."""
    if 1 <= key_num <= 5:
        return (key_num - 1, 2)
    elif 6 <= key_num <= 10:
        return (key_num - 6, 1)
    elif 11 <= key_num <= 15:
        return (key_num - 11, 0)
    return None


def render_notes_submenu(
    categories: list[dict],
) -> bytes:
    """Render the notes category selection screen.

    Args:
        categories: List of dicts with keys: label, icon (optional).
            Up to 14 categories (one slot reserved for BACK).

    Returns:
        JPEG image bytes (480x272)
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    label_font = _get_font(11)
    title_font = _get_font(14)
    back_font = _get_font(12)
    icon_size = 24

    # Title hint — centered at top of screen (between rows)
    title = "NOTES"
    tb = draw.textbbox((0, 0), title, font=title_font)
    tw = tb[2] - tb[0]
    # Place title in the middle row, col 2 area (center of screen)
    center_x = SCREEN_W // 2
    # We'll skip an explicit title — just show the category cards

    # Category cards
    for i, cat in enumerate(categories[:len(_OPTION_KEYS)]):
        key = _OPTION_KEYS[i]
        pos = _key_to_grid(key)
        if pos is None:
            continue
        col, row = pos

        label = cat.get("label", "?")
        icon_name = cat.get("icon")

        # Card with subtle outline
        card_box = _draw_card(
            draw, col, row,
            fill=_darken(_NOTES_COLOR, 0.12),
            outline=_darken(_NOTES_COLOR, 0.4),
        )

        if icon_name:
            # Try to load icon asset
            asset = ICON_ASSETS.get(icon_name, icon_name)
            if isinstance(asset, str):
                tinted = _load_and_tint(asset, _NOTES_COLOR, icon_size)
                if tinted:
                    ix = card_box[0] + (card_box[2] - card_box[0] - icon_size) // 2
                    iy = card_box[1] + 4
                    img.paste(tinted, (ix, iy), tinted)
                    # Label below icon
                    lb = draw.textbbox((0, 0), label, font=label_font)
                    lw = lb[2] - lb[0]
                    lx = card_box[0] + (card_box[2] - card_box[0] - lw) // 2
                    ly = iy + icon_size + 2
                    draw.text((lx, ly), label, fill=_NOTES_COLOR, font=label_font)
                    continue

        # Text-only fallback
        _draw_centered_text(draw, label, card_box, _NOTES_COLOR, label_font)

    # BACK button — key 1 = col 0, row 2
    back_box = _draw_card(draw, 0, 2, fill=BACK_BUTTON_BG)
    _draw_centered_text(draw, "BACK", back_box, SECONDARY_TEXT, back_font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
