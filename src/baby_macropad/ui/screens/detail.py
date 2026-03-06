"""Detail screen factory — parameter selection before logging."""

from __future__ import annotations

from ..framework.primitives import BACK_BUTTON_BG, SECONDARY_TEXT, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Icon, IconLabel, Spacer, Text, TwoLineText

WHITE = (255, 255, 255)


def build_detail_screen(
    title: str,
    options: list[dict],
    timer_seconds: int,
    category_color: tuple[int, int, int],
    hint: str = "Log In",
    subtitle: str | None = None,
    icon: str = "",
    show_log_button: bool = False,
) -> ScreenDef:
    """Build a parameter selection screen with data-page header.

    Layout:
      Row 0 (top):  colored header — icon, title, HOME button
      Row 1 (mid):  option cards centered (e.g. 3 options → keys 7,8,9)
      Row 2 (bot):  BACK card + countdown timer
    All text rendered via cell widgets — no pre_render text.
    """
    cells: dict[int, CellDef] = {}

    # --- Row 0: Colored header (same pattern as data_page) ---
    cells[11] = CellDef(
        widget=Card(fill=category_color, child=Icon(asset_name=icon or "check", color=WHITE, size=36)),
        key_num=11,
    )
    cells[12] = CellDef(widget=Card(fill=category_color, child=Spacer()), key_num=12)
    if subtitle:
        cells[13] = CellDef(
            widget=Card(fill=category_color, child=TwoLineText(
                line1=title, line2=subtitle,
                color1=WHITE, color2=SECONDARY_TEXT,
                font_sizes1=(16, 14, 12), font_sizes2=(10, 9),
                gap=4,
            )),
            key_num=13,
        )
    else:
        cells[13] = CellDef(
            widget=Card(fill=category_color, child=Text(text=title, color=WHITE, font_sizes=(16, 14, 12))),
            key_num=13,
        )
    cells[14] = CellDef(widget=Card(fill=category_color, child=Spacer()), key_num=14)
    # Countdown timer in header row (key 15)
    cells[15] = CellDef(
        widget=Card(
            fill=category_color,
            child=TwoLineText(
                line1=hint,
                line2=str(timer_seconds),
                color1=darken(WHITE, 0.2),
                color2=WHITE,
                font_sizes1=(10, 9),
                font_sizes2=(24, 20, 16),
                gap=6,
            ),
        ),
        key_num=15,
    )

    # --- Row 1: Option cards centered (keys 6-10) ---
    n = len(options)
    start_key = 6 + (5 - n) // 2  # center: 1→8, 2→7, 3→7, 4→6, 5→6
    for i, opt in enumerate(options):
        key_num = opt.get("key_num", start_key + i)
        selected = opt.get("selected", False)
        label = opt.get("label", "?")
        radio_label = f"\u25cf {label}" if selected else f"\u25cb {label}"

        if selected:
            widget = Card(
                fill=darken(category_color, 0.15),
                child=Text(text=radio_label, color=WHITE, font_sizes=(12, 10, 8)),
            )
        else:
            widget = Card(
                fill=darken(category_color, 0.1),
                child=Text(text=radio_label, color=category_color, font_sizes=(12, 10, 8)),
            )

        cells[key_num] = CellDef(
            widget=widget,
            key_num=key_num,
            on_press=f"select_option:{i}",
        )

    # --- Row 2: LOG button (key 5, bottom-right) ---
    if show_log_button:
        cells[5] = CellDef(
            widget=Card(
                fill=category_color,
                child=Text(text="LOG", color=WHITE, font_sizes=(14, 12)),
            ),
            key_num=5,
            on_press="commit_log",
        )

    # --- Row 2: BACK ---
    cells[1] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="BACK", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="back",
    )

    return ScreenDef(name="detail", cells=cells)
