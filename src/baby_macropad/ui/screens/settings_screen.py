"""Settings screen factory — auto-generated from SettingsModel metadata."""

from __future__ import annotations

from ...settings import SettingsModel
from ..framework.primitives import BACK_BUTTON_BG, ICON_COLORS, SECONDARY_TEXT, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Text, TwoLineText

_SETTINGS_COLOR = ICON_COLORS.get("settings", (200, 200, 200))

# Settings cards fill keys starting from top-left: 11, 12, 13, 14, 15, 6, 7...
_SETTING_KEYS = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10]


def _format_value(field_name: str, value, extra: dict) -> str:
    """Format a settings value for display."""
    fmt = extra.get("format")
    if fmt:
        return fmt.format(value=value)
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    # Map known string values to short labels
    style_map = {
        "flash": "Flash",
        "starburst": "Burst",
        "sparkle": "Sparkle",
        "spotlight": "Spot",
        "none": "Off",
    }
    if isinstance(value, str) and value in style_map:
        return style_map[value]
    return str(value)


def build_settings_screen(settings: SettingsModel) -> ScreenDef:
    """Auto-generate the settings screen from SettingsModel field metadata.

    Fields with json_schema_extra (and not hidden) become TwoLineText cards.
    """
    cells: dict[int, CellDef] = {}

    key_idx = 0
    for field_name, field_info in type(settings).model_fields.items():
        extra = field_info.json_schema_extra or {}
        if extra.get("hidden"):
            continue
        if key_idx >= len(_SETTING_KEYS):
            break

        key_num = _SETTING_KEYS[key_idx]
        key_idx += 1

        display_label = extra.get("display_label", field_name)
        value = getattr(settings, field_name)
        display_value = _format_value(field_name, value, extra)

        widget = Card(
            fill=darken(_SETTINGS_COLOR, 0.12),
            outline=darken(_SETTINGS_COLOR, 0.3),
            child=TwoLineText(
                line1=display_label,
                line2=display_value,
                color1=SECONDARY_TEXT,
                color2=_SETTINGS_COLOR,
            ),
        )

        cells[key_num] = CellDef(
            widget=widget,
            key_num=key_num,
            on_press=f"cycle:{field_name}",
        )

    # Title in cell at key 8 (col 2, row 1) — only if not used by a setting card
    if 8 not in cells:
        cells[8] = CellDef(
            widget=Text(
                text="SETTINGS", color=_SETTINGS_COLOR, font_sizes=(14, 12, 10)
            ),
            key_num=8,
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

    return ScreenDef(name="settings", cells=cells)
