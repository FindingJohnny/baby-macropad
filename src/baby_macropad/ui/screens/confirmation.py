"""Confirmation screen factory — post-log celebration with color header."""

from __future__ import annotations

from ..framework.primitives import BACK_BUTTON_BG, SECONDARY_TEXT
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Icon, Spacer, Text, TwoLineText


def build_confirmation_screen(
    action_label: str,
    context_line: str,
    category_color: tuple[int, int, int],
    resource_id: str | None = None,
) -> ScreenDef:
    """Build the confirmation screen with color header + DONE button.

    Layout (5x3 grid):
      Row 0 (keys 11-15): Full category color fill, checkmark at key 13
      Row 1 (keys 6-10):  Dark bg. Label at key 8, context at key 9
      Row 2 (keys 1-5):   Dark bg. UNDO at key 1 (if resource_id), DONE at key 5
    """
    cells: dict[int, CellDef] = {}

    # --- Top row: color header with checkmark ---
    for key in (11, 12, 14, 15):
        cells[key] = CellDef(
            widget=Card(fill=category_color, child=Spacer()),
            key_num=key,
        )
    cells[13] = CellDef(
        widget=Card(
            fill=category_color,
            child=Icon(asset_name="check", color=(255, 255, 255), size=36),
        ),
        key_num=13,
    )

    # --- Middle row: label + context ---
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

    if context_line:
        cells[9] = CellDef(
            widget=Text(
                text=context_line, color=SECONDARY_TEXT, font_sizes=(11, 10, 9)
            ),
            key_num=9,
        )

    # --- Bottom row: UNDO + DONE ---
    if resource_id:
        cells[1] = CellDef(
            widget=Card(
                fill=BACK_BUTTON_BG,
                child=Text(text="UNDO", color=SECONDARY_TEXT, font_sizes=(12, 10)),
            ),
            key_num=1,
            on_press="undo",
        )

    cells[5] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="DONE", color=(255, 255, 255), font_sizes=(12, 10)),
        ),
        key_num=5,
        on_press="done",
    )

    return ScreenDef(name="confirmation", cells=cells)
