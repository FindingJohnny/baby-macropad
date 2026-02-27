"""Confirmation screen factory — post-log celebration."""

from __future__ import annotations

from ..framework.icon_cache import load_and_tint, load_composite
from ..framework.primitives import (
    BACK_BUTTON_BG,
    ICON_ASSETS,
    SECONDARY_TEXT,
    SCREEN_W,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    darken,
)
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Spacer, Text
from ..framework.text_engine import get_font


def build_confirmation_screen(
    action_label: str,
    context_line: str,
    icon_name: str,
    category_color: tuple[int, int, int],
    celebration_style: str = "color_fill",
    column_index: int = 0,
) -> ScreenDef:
    """Build the post-log celebration screen.

    The column fill celebration is drawn via pre_render. Icon, label, and
    context are also pre_render since they are centered in the column and
    across the screen — not grid-cell-aligned.
    Key 1 is always the UNDO cell.
    """
    col = max(0, min(4, column_index))

    def _pre_render(img, draw):
        # Column fill celebration
        if celebration_style == "color_fill" and 0 <= col <= 4:
            fill_color = darken(category_color, 0.4)
            col_x = VIS_COL_X[col]
            col_w = VIS_COL_W[col]
            for row in range(3):
                ry = VIS_ROW_Y[row]
                rh = VIS_ROW_H[row]
                draw.rounded_rectangle(
                    [col_x, ry, col_x + col_w, ry + rh],
                    radius=6,
                    fill=fill_color,
                )

        # Icon in top cell of column
        icon_size = 36
        asset = ICON_ASSETS.get(icon_name, icon_name)
        tinted = None
        if isinstance(asset, tuple):
            tinted = load_composite(asset[0], asset[1], (255, 255, 255), icon_size)
        else:
            tinted = load_and_tint(asset, (255, 255, 255), icon_size)
        if tinted:
            ix = VIS_COL_X[col] + (VIS_COL_W[col] - icon_size) // 2
            iy = VIS_ROW_Y[0] + (VIS_ROW_H[0] - icon_size) // 2
            img.paste(tinted, (ix, iy), tinted)

        # Action label in middle cell of column
        label_font = get_font(14, bold=True)
        lb = draw.textbbox((0, 0), action_label, font=label_font)
        lw = lb[2] - lb[0]
        lh = lb[3] - lb[1]
        lx = VIS_COL_X[col] + (VIS_COL_W[col] - lw) // 2
        ly = VIS_ROW_Y[1] + (VIS_ROW_H[1] - lh) // 2
        draw.text((lx, ly), action_label, fill=(255, 255, 255), font=label_font)

        # Context line full-width in bottom row
        if context_line:
            context_font = get_font(11, bold=True)
            cb = draw.textbbox((0, 0), context_line, font=context_font)
            cw = cb[2] - cb[0]
            ch = cb[3] - cb[1]
            cx = (SCREEN_W - cw) // 2
            cy = VIS_ROW_Y[2] + (VIS_ROW_H[2] - ch) // 2
            draw.text((cx, cy), context_line, fill=SECONDARY_TEXT, font=context_font)

    cells: dict[int, CellDef] = {}

    # UNDO button at key 1
    cells[1] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="UNDO", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="undo",
    )

    return ScreenDef(name="confirmation", cells=cells, pre_render=_pre_render)
