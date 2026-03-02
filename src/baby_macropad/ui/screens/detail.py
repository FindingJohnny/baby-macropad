"""Detail screen factory — parameter selection before logging."""

from __future__ import annotations

from ..framework.primitives import BACK_BUTTON_BG, SECONDARY_TEXT, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Text, TwoLineText


def build_detail_screen(
    title: str,
    options: list[dict],
    timer_seconds: int,
    category_color: tuple[int, int, int],
    hint: str = "Log In",
    subtitle: str | None = None,
) -> ScreenDef:
    """Build a parameter selection screen.

    Layout:
      Top row: option cards centered (e.g. 3 options → keys 12,13,14)
      Key 8 (col 2, row 1): "Log In" label on top + BIG countdown number below
      Key 7 (col 1, row 1): title card (optionally with subtitle)
      Key 1 (col 0, row 2): BACK card
    All text rendered via cell widgets — no pre_render text.
    """
    cells: dict[int, CellDef] = {}

    # Option cards — centered in top row (keys 11-15)
    n = len(options)
    start_key = 11 + (5 - n) // 2  # center: 1→13, 2→12, 3→12, 4→11, 5→11
    for i, opt in enumerate(options):
        key_num = opt.get("key_num", start_key + i)
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
            on_press=f"select_option:{i}",
        )

    # Countdown card — key 8 (col 2, row 1) — label on top, BIG number below
    cells[8] = CellDef(
        widget=Card(
            fill=darken(category_color, 0.15),
            child=TwoLineText(
                line1=hint,
                line2=str(timer_seconds),
                color1=SECONDARY_TEXT,
                color2=category_color,
                font_sizes1=(10, 9),
                font_sizes2=(24, 20, 16),
                gap=6,
            ),
        ),
        key_num=8,
    )

    # Title card — key 7 (col 1, row 1) — optionally with subtitle
    if subtitle:
        title_widget = Card(
            fill=darken(category_color, 0.08),
            child=TwoLineText(
                line1=title,
                line2=subtitle,
                color1=(255, 255, 255),
                color2=SECONDARY_TEXT,
                font_sizes1=(14, 12, 10),
                font_sizes2=(10, 9),
                gap=4,
            ),
        )
    else:
        title_widget = Card(
            fill=darken(category_color, 0.08),
            child=Text(text=title, color=(255, 255, 255), font_sizes=(14, 12, 10)),
        )
    cells[7] = CellDef(widget=title_widget, key_num=7)

    # BACK button — key 1 (col 0, row 2)
    cells[1] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="BACK", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="back",
    )

    return ScreenDef(name="detail", cells=cells)
