"""Selection screen factory — generic grid for category picking."""

from __future__ import annotations

from ..framework.icon_cache import load_and_tint
from ..framework.primitives import BACK_BUTTON_BG, ICON_ASSETS, SECONDARY_TEXT, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, IconLabel, Text


# Key layout: top row first (11-15), middle row (6-10), bottom row (2-5)
# Key 1 reserved for BACK
_OPTION_KEYS = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 2, 3, 4, 5]


def build_selection_screen(
    items: list[dict],
    accent_color: tuple[int, int, int],
    title: str | None = None,
) -> ScreenDef:
    """Build a generic grid selection screen. Up to 14 items.

    Args:
        items: List of dicts with keys: label, icon (optional).
        accent_color: RGB accent color for cards.
        title: Optional title (unused for now, reserved for future).
    """
    cells: dict[int, CellDef] = {}

    for i, item in enumerate(items[: len(_OPTION_KEYS)]):
        key = _OPTION_KEYS[i]
        label = item.get("label", "?")
        icon_name = item.get("icon")

        if icon_name:
            widget = Card(
                fill=darken(accent_color, 0.12),
                outline=darken(accent_color, 0.4),
                child=IconLabel(
                    icon_name=icon_name,
                    label=label,
                    color=accent_color,
                    icon_size=24,
                ),
            )
        else:
            widget = Card(
                fill=darken(accent_color, 0.12),
                outline=darken(accent_color, 0.4),
                child=Text(text=label, color=accent_color, font_sizes=(11, 10, 8)),
            )

        cells[key] = CellDef(
            widget=widget,
            key_num=key,
            on_press=f"select:{i}",
        )

    # BACK button at key 1
    cells[1] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="BACK", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="back",
    )

    return ScreenDef(name="selection", cells=cells)
