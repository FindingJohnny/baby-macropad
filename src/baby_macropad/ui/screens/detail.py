"""Detail screen factory — parameter selection before logging."""

from __future__ import annotations

from ..framework.primitives import BACK_BUTTON_BG, SECONDARY_TEXT, SCREEN_W, VIS_COL_W, VIS_COL_X, VIS_ROW_H, VIS_ROW_Y, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Text
from ..framework.text_engine import get_font


def build_detail_screen(
    title: str,
    options: list[dict],
    timer_seconds: int,
    category_color: tuple[int, int, int],
) -> ScreenDef:
    """Build a parameter selection screen.

    Layout:
      Top row (keys 11-14): option cards (selected=filled, unselected=outlined)
      Key 10 (col 4, row 1): timer countdown card
      Key 1 (col 0, row 2): BACK card
    pre_render draws the title centered across cols 1-3 in the middle row.
    """
    cells: dict[int, CellDef] = {}

    # Option cards in top row (keys 11-14)
    for opt in options:
        key_num = opt.get("key_num", 11)
        selected = opt.get("selected", False)
        label = opt.get("label", "?")

        if selected:
            widget = Card(
                fill=category_color,
                child=Text(text=label, color=(255, 255, 255), font_sizes=(12, 10, 8)),
            )
        else:
            widget = Card(
                fill=darken(category_color, 0.1),
                outline=category_color,
                child=Text(text=label, color=category_color, font_sizes=(12, 10, 8)),
            )

        cells[key_num] = CellDef(
            widget=widget,
            key_num=key_num,
            on_press=f"select_option:{key_num - 11}",
        )

    # Timer card — key 10 (col 4, row 1)
    timer_text = f"{timer_seconds}s"
    cells[10] = CellDef(
        widget=Card(
            fill=darken(category_color, 0.30),
            child=Text(text=timer_text, color=category_color, font_sizes=(14, 12, 10)),
        ),
        key_num=10,
    )

    # BACK button — key 1 (col 0, row 2)
    cells[1] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="BACK", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="back",
    )

    # Title + instruction rendered via pre_render (spans cols 1-3, centered in middle row)
    def _draw_title(img, draw):
        title_font = get_font(16, bold=True)
        tb = draw.textbbox((0, 0), title, font=title_font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        center_x = (VIS_COL_X[1] + VIS_COL_X[3] + VIS_COL_W[3]) // 2
        ty = VIS_ROW_Y[1] + (VIS_ROW_H[1] - th) // 2 - 8
        draw.text((center_x - tw // 2, ty), title, fill=(255, 255, 255), font=title_font)

        # Instruction hint below title
        hint_font = get_font(10, bold=True)
        hint = "tap option or wait"
        hb = draw.textbbox((0, 0), hint, font=hint_font)
        hw = hb[2] - hb[0]
        draw.text((center_x - hw // 2, ty + th + 4), hint, fill=SECONDARY_TEXT, font=hint_font)

    return ScreenDef(name="detail", cells=cells, pre_render=_draw_title)
