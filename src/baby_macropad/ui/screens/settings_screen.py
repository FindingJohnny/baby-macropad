"""Settings screen factory — auto-generated from SettingsModel metadata."""

from __future__ import annotations

from ...settings import SettingsModel
from ..framework.primitives import BACK_BUTTON_BG, ICON_COLORS, SCREEN_W, SECONDARY_TEXT, VIS_ROW_H, VIS_ROW_Y, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Text, TwoLineText
from ..framework.text_engine import get_font

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
        "color_fill": "Fill",
        "radiate": "Glow",
        "randomize": "Fun",
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

    # Title via pre_render — centered in middle row
    def _draw_title(img, draw):
        title_font = get_font(14, bold=True)
        title = "SETTINGS"
        tb = draw.textbbox((0, 0), title, font=title_font)
        tw = tb[2] - tb[0]
        tx = (SCREEN_W - tw) // 2
        ty = VIS_ROW_Y[1] + (VIS_ROW_H[1] - (tb[3] - tb[1])) // 2
        draw.text((tx, ty), title, fill=_SETTINGS_COLOR, font=title_font)

    # BACK button at key 1
    cells[1] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="BACK", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="back",
    )

    return ScreenDef(name="settings", cells=cells, pre_render=_draw_title)
