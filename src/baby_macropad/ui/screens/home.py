"""Home grid screen factory — 15 IconLabel buttons."""

from __future__ import annotations

from typing import Any

from ..framework.primitives import ICON_COLORS, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, IconLabel, Spacer, Text
from ..framework.text_engine import get_font


def build_home_grid(
    buttons: dict[int, Any],
    runtime_state: dict[int, str] | None = None,
) -> ScreenDef:
    """Build the main 15-button home grid.

    Args:
        buttons: Key number (1-15) to button config (dict or object with icon/label attrs).
        runtime_state: Key number to state string. Sleep key: "active:Xh Ym",
            breast keys: "suggested".
    """
    runtime_state = runtime_state or {}
    cells: dict[int, CellDef] = {}

    for key_num, button in buttons.items():
        icon_name = button.icon if hasattr(button, "icon") else button.get("icon", "")
        label = button.label if hasattr(button, "label") else button.get("label", "?")
        color = ICON_COLORS.get(icon_name, (200, 200, 200))
        state = runtime_state.get(key_num, "idle")

        is_sleep_active = icon_name == "sleep" and state.startswith("active")
        is_suggested = state == "suggested"

        if is_sleep_active:
            # Active sleep: sunrise icon + WAKE UP + elapsed time
            elapsed = state.split(":", 1)[1] if ":" in state else ""
            wake_label = "WAKE UP"
            if elapsed:
                wake_label = f"WAKE UP\n{elapsed}"
            card_bg = darken(color, 0.12)
            widget = Card(
                fill=card_bg,
                child=IconLabel(
                    icon_name="sunrise",
                    label="WAKE UP",
                    color=color,
                    icon_size=26,
                    badge=elapsed or None,
                ),
            )
        else:
            card_bg_factor = 0.18 if is_suggested else 0.12
            badge = "\u25b6 NEXT" if is_suggested and icon_name in ("breast_left", "breast_right") else None
            widget = Card(
                fill=darken(color, card_bg_factor),
                child=IconLabel(
                    icon_name=icon_name,
                    label=label,
                    color=color,
                    badge=badge,
                ),
            )

        cells[key_num] = CellDef(
            widget=widget,
            key_num=key_num,
            on_press=f"home:{button.action if hasattr(button, 'action') else button.get('action', icon_name)}",
        )

    return ScreenDef(name="home_grid", cells=cells)
