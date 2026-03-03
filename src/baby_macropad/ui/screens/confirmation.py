"""Confirmation screen factory — post-log celebration with compass rose."""

from __future__ import annotations

from ..framework.primitives import (
    BACK_BUTTON_BG,
    SECONDARY_TEXT,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    darken,
    key_to_grid,
)
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Icon, Text, TwoLineText

# Cell groups for compass rose animation (expanding from center)
_CENTER = {8}
_CARDINAL = {7, 9, 12, 2}
_DIAGONAL = {11, 13, 1, 3}
_EDGES = {6, 10, 15, 5, 14, 4}

# How many groups are visible per animation frame
_FRAME_GROUPS = [
    _CENTER,
    _CENTER | _CARDINAL,
    _CENTER | _CARDINAL | _DIAGONAL,
    _CENTER | _CARDINAL | _DIAGONAL | _EDGES,  # full compass
]


def build_confirmation_screen(
    action_label: str,
    context_line: str,
    icon_name: str,
    category_color: tuple[int, int, int],
    celebration_style: str = "color_fill",
    column_index: int = 0,
    celebration_frame: int = 3,
) -> ScreenDef:
    """Build the post-log celebration screen with compass rose.

    Compass rose: cells light up radially from center outward.
    celebration_frame controls the animation stage (0=center only, 3=full).
    Icon at key 13 (top center), label at key 8 (center),
    context at key 3 (below center), UNDO at key 1.
    """
    lit_keys = _FRAME_GROUPS[min(celebration_frame, len(_FRAME_GROUPS) - 1)]

    def _pre_render(img, draw):
        # Draw compass rose glow — cells light up based on animation frame
        for key in lit_keys:
            grid = key_to_grid(key)
            if not grid:
                continue
            col, row = grid
            cx = VIS_COL_X[col]
            cy = VIS_ROW_Y[row]
            cw = VIS_COL_W[col]
            ch = VIS_ROW_H[row]

            # Brightness varies by distance from center
            if key in _CENTER:
                fill = darken(category_color, 0.7)
            elif key in _CARDINAL:
                fill = darken(category_color, 0.5)
            elif key in _DIAGONAL:
                fill = darken(category_color, 0.35)
            else:
                fill = darken(category_color, 0.25)

            draw.rounded_rectangle(
                [cx, cy, cx + cw, cy + ch],
                radius=6,
                fill=fill,
            )

    cells: dict[int, CellDef] = {}

    # Icon at key 13 (top center)
    cells[13] = CellDef(
        widget=Icon(asset_name=icon_name, color=(255, 255, 255), size=36),
        key_num=13,
    )

    # Action label at key 8 (center) — supports newline for two-line labels
    if "\n" in action_label:
        parts = action_label.split("\n", 1)
        label_widget = TwoLineText(
            line1=parts[0],
            line2=parts[1],
            color1=(255, 255, 255),
            color2=(255, 255, 255),
            font_sizes1=(14, 12, 10),
            font_sizes2=(14, 12, 10),
        )
    else:
        label_widget = Text(
            text=action_label, color=(255, 255, 255), font_sizes=(18, 14, 12)
        )
    cells[8] = CellDef(widget=label_widget, key_num=8)

    # Context line at key 3 (below center)
    if context_line:
        cells[3] = CellDef(
            widget=Text(
                text=context_line, color=SECONDARY_TEXT, font_sizes=(11, 10, 9)
            ),
            key_num=3,
        )

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
