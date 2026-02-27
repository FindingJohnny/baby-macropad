"""Confirmation screen renderer — shown after successful event logging.

Displays a celebration with the action icon, label, context hint,
and an UNDO button. Shown for ~2 seconds before returning to the
main button grid.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageDraw

from .icons import (
    BG_COLOR,
    SCREEN_H,
    SCREEN_W,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    _get_font,
    _load_and_tint,
)

logger = logging.getLogger(__name__)

_SECONDARY_TEXT = (142, 142, 147)
_CARD_RADIUS = 6
_CARD_MARGIN = 2


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def render_confirmation(
    action_label: str,
    context_line: str,
    icon_name: str,
    category_color: tuple[int, int, int],
    celebration_style: str = "color_fill",
    column_index: int = 0,
) -> bytes:
    """Render a confirmation/celebration screen after logging.

    Args:
        action_label: Main text, e.g. "Left breast logged"
        context_line: Secondary text, e.g. "Next: Right breast"
        icon_name: Tabler icon asset name (e.g. "bottle", "moon")
        category_color: RGB tuple for the category accent color
        celebration_style: "color_fill" highlights a column, "none" for plain
        column_index: Which column (0-4) to highlight for color_fill style

    Returns:
        JPEG image bytes (480x272)
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Color fill celebration — fill the action's column cells at ~40% brightness
    if celebration_style == "color_fill" and 0 <= column_index <= 4:
        fill_color = _darken(category_color, 0.4)
        col_x = VIS_COL_X[column_index]
        col_w = VIS_COL_W[column_index]
        for row in range(3):
            ry = VIS_ROW_Y[row]
            rh = VIS_ROW_H[row]
            draw.rounded_rectangle(
                [col_x, ry, col_x + col_w, ry + rh],
                radius=6,
                fill=fill_color,
            )

    # Center content: icon + action_label + context_line
    label_font = _get_font(22)
    context_font = _get_font(14)
    icon_size = 56

    # Calculate vertical layout of centered content
    label_bbox = draw.textbbox((0, 0), action_label, font=label_font)
    label_h = label_bbox[3] - label_bbox[1]
    context_bbox = draw.textbbox((0, 0), context_line, font=context_font)
    context_h = context_bbox[3] - context_bbox[1]

    gap = 8
    total_h = icon_size + gap + label_h + gap + context_h
    top_y = (SCREEN_H - total_h) // 2
    center_x = SCREEN_W // 2

    # Icon (tinted Tabler asset)
    tinted = _load_and_tint(icon_name, category_color, icon_size)
    if tinted:
        ix = center_x - icon_size // 2
        img.paste(tinted, (ix, top_y), tinted)

    # Action label
    label_w = label_bbox[2] - label_bbox[0]
    draw.text(
        (center_x - label_w // 2, top_y + icon_size + gap),
        action_label,
        fill=(255, 255, 255),
        font=label_font,
    )

    # Context line
    context_w = context_bbox[2] - context_bbox[0]
    draw.text(
        (center_x - context_w // 2, top_y + icon_size + gap + label_h + gap),
        context_line,
        fill=_SECONDARY_TEXT,
        font=context_font,
    )

    # UNDO button — bottom-left (key 1 = col 0, row 2)
    undo_font = _get_font(12)
    ux = VIS_COL_X[0] + _CARD_MARGIN
    uy = VIS_ROW_Y[2] + _CARD_MARGIN
    uw = VIS_COL_W[0] - _CARD_MARGIN * 2
    uh = VIS_ROW_H[2] - _CARD_MARGIN * 2
    draw.rounded_rectangle(
        [ux, uy, ux + uw, uy + uh],
        radius=6,
        fill=(38, 38, 40),
    )
    # Center "UNDO" in the card
    ub = draw.textbbox((0, 0), "UNDO", font=undo_font)
    utw = ub[2] - ub[0]
    uth = ub[3] - ub[1]
    draw.text(
        (ux + (uw - utw) // 2, uy + (uh - uth) // 2),
        "UNDO",
        fill=_SECONDARY_TEXT,
        font=undo_font,
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
