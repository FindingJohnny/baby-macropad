"""Sleep mode screen factory — full-screen takeover during active sleep."""

from __future__ import annotations

from ..framework.icon_cache import load_and_tint
from ..framework.primitives import ICON_COLORS, SCREEN_H, SCREEN_W, SECONDARY_TEXT, VIS_COL_W, VIS_COL_X, VIS_ROW_H, VIS_ROW_Y
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Spacer, Text
from ..framework.text_engine import get_font

_SLEEP_BLUE = ICON_COLORS.get("sleep", (102, 153, 204))
_DIM_SECONDARY = (90, 90, 94)


def build_sleep_screen(
    elapsed_minutes: int,
    start_time_str: str,
) -> ScreenDef:
    """Build the full-screen sleep mode takeover.

    Central content (moon, elapsed time, etc.) is rendered via pre_render.
    Key 13: dim WAKE UP card. All other keys: wake_screen action.
    """
    # Format elapsed time
    if elapsed_minutes >= 60:
        hours = elapsed_minutes // 60
        mins = elapsed_minutes % 60
        elapsed_text = f"{hours}h {mins}m"
    else:
        elapsed_text = f"{elapsed_minutes}m"

    def _pre_render(img, draw):
        label_font = get_font(18, bold=True)
        time_font = get_font(30, bold=True)
        small_font = get_font(13, bold=True)

        icon_size = 64
        gap = 6

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
        tinted = load_and_tint("moon", _SLEEP_BLUE, icon_size)
        if tinted:
            ix = center_x - icon_size // 2
            img.paste(tinted, (ix, top_y), tinted)

        # "sleeping..."
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

    cells: dict[int, CellDef] = {}

    # WAKE UP at key 13 (col 2, row 0)
    cells[13] = CellDef(
        widget=Card(
            fill=(38, 38, 40),
            child=Text(text="WAKE UP", color=_DIM_SECONDARY, font_sizes=(11, 10, 8)),
        ),
        key_num=13,
        on_press="wake_up",
    )

    # All other keys: wake_screen (just brightens display)
    for key in range(1, 16):
        if key == 13:
            continue
        cells[key] = CellDef(
            widget=Spacer(),
            key_num=key,
            on_press="wake_screen",
        )

    return ScreenDef(name="sleep", cells=cells, pre_render=_pre_render)
