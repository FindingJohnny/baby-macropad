"""Shared constants, grid geometry, and utility functions.

Extracted from icons.py to eliminate duplication across renderers.
All renderers should import constants from here (via icons.py re-exports
for backward compatibility, or directly for new code).
"""

from __future__ import annotations

from dataclasses import dataclass

# M18 screen dimensions
SCREEN_W = 480
SCREEN_H = 272
COLS = 5
ROWS = 3
CELL_W = SCREEN_W // COLS  # 96

# Visible area per button — measured via calibration patterns.
# The physical bezels obscure ~12px on each side horizontally and
# ~15-20px on each side vertically. These are the pixel rectangles
# actually visible through the button cutouts.
#
# Columns (X ranges): C0=11-83, C1=107-179, C2=203-275, C3=299-371, C4=395-467
# Rows (Y ranges):    R0=10-70,  R1=110-170, R2=200-270
VIS_COL_X = [11, 107, 203, 299, 395]  # Left edge of visible area per column
VIS_COL_W = [72, 72, 72, 72, 72]      # Visible width per column
VIS_ROW_Y = [10, 110, 200]            # Top edge of visible area per row
VIS_ROW_H = [60, 60, 70]              # Visible height per row

BG_COLOR = (28, 28, 30)  # Near-black, matches iOS bbBackground dark

# Shared design tokens — used by all renderers
SECONDARY_TEXT = (142, 142, 147)  # iOS secondaryLabel equivalent
CARD_RADIUS = 6
CARD_MARGIN = 2
BACK_BUTTON_BG = (38, 38, 40)

# Category colors (same as iOS design system)
ICON_COLORS = {
    "breast_left": (102, 204, 102),   # Soft green
    "breast_right": (102, 204, 102),
    "bottle": (102, 204, 102),
    "pump": (102, 204, 102),
    "diaper_pee": (204, 170, 68),     # Warm amber
    "diaper_poop": (204, 170, 68),
    "diaper_both": (204, 170, 68),
    "sleep": (102, 153, 204),         # Soft blue
    "note": (153, 153, 153),          # Warm gray
    "settings": (200, 200, 200),      # Neutral gray
    "light": (255, 204, 0),           # Yellow
    "fan": (0, 204, 204),             # Cyan
    "sound": (180, 180, 180),         # Light gray
    "scene_off": (255, 255, 255),     # White
}

# Map icon names to PNG asset files (same Tabler icons as iOS app).
# String values map to a single asset file. Tuple values trigger composite
# rendering via load_composite (first icon top-left, second bottom-right).
ICON_ASSETS: dict[str, str | tuple[str, str]] = {
    "breast_left": "letter_l",
    "breast_right": "letter_r",
    "bottle": "bottle",
    "pump": "pump",
    "diaper_pee": "diaper",
    "diaper_poop": "poo",
    "diaper_both": ("poo", "diaper"),
    "sleep": "moon",
    "note": "note",
    "settings": "gear",
    "pill": "pill",
    "thermometer": "thermometer",
    "star": "star",
}

# Labels shown below the icon
ICON_LABELS = {
    "breast_left": "LEFT",
    "breast_right": "RIGHT",
    "bottle": "BOTTLE",
    "pump": "PUMP",
    "diaper_pee": "PEE",
    "diaper_poop": "POOP",
    "diaper_both": "BOTH",
    "sleep": "SLEEP",
    "note": "NOTES",
    "settings": "SETTINGS",
    "light": "LIGHT",
    "fan": "FAN",
    "sound": "SOUND",
    "scene_off": "OFF",
    "pill": "MEDS",
    "thermometer": "TEMP",
    "star": "MILSTN",
}


@dataclass
class Rect:
    """Axis-aligned rectangle."""

    x: int
    y: int
    w: int
    h: int


def darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Darken an RGB color by a multiplicative factor (0.0 = black, 1.0 = unchanged)."""
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def key_to_grid(key_num: int) -> tuple[int, int] | None:
    """Key number (1-15) to grid (col, row).

    M18 physical-to-key mapping (verified by testing):
      Top row:    KEY_11  KEY_12  KEY_13  KEY_14  KEY_15
      Middle row: KEY_6   KEY_7   KEY_8   KEY_9   KEY_10
      Bottom row: KEY_1   KEY_2   KEY_3   KEY_4   KEY_5

    Top and bottom rows are swapped vs naive numbering.
    """
    if key_num < 1 or key_num > 15:
        return None
    if 1 <= key_num <= 5:
        # Keys 1-5 are on the BOTTOM row (row 2)
        return (key_num - 1, 2)
    elif 6 <= key_num <= 10:
        # Keys 6-10 are in the MIDDLE row (row 1)
        return (key_num - 6, 1)
    else:
        # Keys 11-15 are on the TOP row (row 0)
        return (key_num - 11, 0)
