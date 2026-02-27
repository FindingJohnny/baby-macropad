"""Sleep mode renderer — full-screen takeover during active baby sleep.

Shows a moon icon, elapsed time, start time, and a dim WAKE UP hint.
Designed to be calm and low-brightness for nighttime use.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageDraw

from .icons import (
    BG_COLOR,
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

_SLEEP_BLUE = ICON_COLORS.get("sleep", (102, 153, 204))
_DIM_SECONDARY = (90, 90, 94)


def render_sleep_mode(
    elapsed_minutes: int,
    start_time_str: str,
) -> bytes:
    """Render the sleep mode takeover screen.

    Args:
        elapsed_minutes: Minutes since sleep started
        start_time_str: Human-readable start time, e.g. "10:14 PM"

    Returns:
        JPEG image bytes (480x272)
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    label_font = _get_font(18)
    time_font = _get_font(30)
    small_font = _get_font(13)
    hint_font = _get_font(11)

    # Format elapsed time
    if elapsed_minutes >= 60:
        hours = elapsed_minutes // 60
        mins = elapsed_minutes % 60
        elapsed_text = f"{hours}h {mins}m"
    else:
        elapsed_text = f"{elapsed_minutes}m"

    # Vertical layout: moon icon, "sleeping...", elapsed time, "started X:XX PM"
    icon_size = 64
    gap = 6

    # Measure text heights
    label_text = "sleeping..."
    label_bbox = draw.textbbox((0, 0), label_text, font=label_font)
    label_h = label_bbox[3] - label_bbox[1]

    time_bbox = draw.textbbox((0, 0), elapsed_text, font=time_font)
    time_h = time_bbox[3] - time_bbox[1]

    started_text = f"started {start_time_str}"
    started_bbox = draw.textbbox((0, 0), started_text, font=small_font)
    started_h = started_bbox[3] - started_bbox[1]

    total_h = icon_size + gap + label_h + gap + time_h + gap + started_h
    top_y = (SCREEN_H - total_h) // 2
    center_x = SCREEN_W // 2

    # Moon icon
    tinted = _load_and_tint("moon", _SLEEP_BLUE, icon_size)
    if tinted:
        ix = center_x - icon_size // 2
        img.paste(tinted, (ix, top_y), tinted)

    # "sleeping..." label
    label_w = label_bbox[2] - label_bbox[0]
    draw.text(
        (center_x - label_w // 2, top_y + icon_size + gap),
        label_text,
        fill=SECONDARY_TEXT,
        font=label_font,
    )

    # Elapsed time (large, blue)
    time_w = time_bbox[2] - time_bbox[0]
    draw.text(
        (center_x - time_w // 2, top_y + icon_size + gap + label_h + gap),
        elapsed_text,
        fill=_SLEEP_BLUE,
        font=time_font,
    )

    # "started X:XX PM"
    started_w = started_bbox[2] - started_bbox[0]
    draw.text(
        (center_x - started_w // 2, top_y + icon_size + gap + label_h + gap + time_h + gap),
        started_text,
        fill=_DIM_SECONDARY,
        font=small_font,
    )

    # WAKE UP hint — key 13 position (col 2, row 0)
    wx = VIS_COL_X[2] + 2
    wy = VIS_ROW_Y[0] + 2
    ww = VIS_COL_W[2] - 4
    wh = VIS_ROW_H[0] - 4
    # Draw subtle card
    draw.rounded_rectangle(
        [wx, wy, wx + ww, wy + wh],
        radius=6,
        fill=(38, 38, 40),
    )
    # Center "WAKE UP" text
    wake_text = "WAKE UP"
    wb = draw.textbbox((0, 0), wake_text, font=hint_font)
    wtw = wb[2] - wb[0]
    wth = wb[3] - wb[1]
    draw.text(
        (wx + (ww - wtw) // 2, wy + (wh - wth) // 2),
        wake_text,
        fill=_DIM_SECONDARY,
        font=hint_font,
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
