"""Setup screen factories for the pairing flow.

Two screens:
1. Name selection — reuses the selection grid pattern
2. QR code display — reuses the data page layout with QR in pre_render
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..framework.primitives import (
    BACK_BUTTON_BG,
    SECONDARY_TEXT,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    darken,
)
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Icon, Spacer, Text
from .data_page import DataColumn, PageAction, build_data_page
from .selection import build_selection_screen

_SETUP_COLOR = (100, 149, 237)  # Cornflower blue — distinct from other categories

NAME_PRESETS = ["Nursery", "Bedroom", "Kitchen", "Living Rm"]


def build_setup_name_screen() -> ScreenDef:
    """Build the name selection screen for setup.

    Shows 4 preset location names in the top row (same pattern as notes submenu).
    """
    items = [{"label": name} for name in NAME_PRESETS]
    return build_selection_screen(items, accent_color=_SETUP_COLOR, title="SETUP")


def build_setup_qr_screen(
    qr_image: Image.Image,
    name: str,
    code: str,
    status: str = "Waiting...",
) -> ScreenDef:
    """Build the QR code display screen for pairing.

    Layout:
      Row 0: Colored header — link icon, "SETUP" title
      Row 1: [QR code cell] [NAME label] [CODE label] [STATUS label]
      Row 2: [BACK]         [name value] [code value] [status value]

    The QR code is rendered via pre_render into the R1C0+R2C0 area (keys 6 and 1 zone).
    """
    cells: dict[int, CellDef] = {}

    # --- Row 0: Header ---
    cells[11] = CellDef(
        widget=Card(fill=_SETUP_COLOR, child=Icon(asset_name="link", color=(255, 255, 255), size=36)),
        key_num=11,
    )
    cells[12] = CellDef(widget=Card(fill=_SETUP_COLOR, child=Spacer()), key_num=12)
    cells[13] = CellDef(
        widget=Card(fill=_SETUP_COLOR, child=Text(text="SETUP", color=(255, 255, 255), font_sizes=(16, 14, 12))),
        key_num=13,
    )
    cells[14] = CellDef(widget=Card(fill=_SETUP_COLOR, child=Spacer()), key_num=14)
    cells[15] = CellDef(widget=Card(fill=_SETUP_COLOR, child=Spacer()), key_num=15)

    # --- Row 1: Labels (cols 1-3) ---
    cells[7] = CellDef(
        widget=Text(text="NAME", color=SECONDARY_TEXT, font_sizes=(11, 10, 9), valign="bottom"),
        key_num=7,
    )
    cells[8] = CellDef(
        widget=Text(text="CODE", color=SECONDARY_TEXT, font_sizes=(11, 10, 9), valign="bottom"),
        key_num=8,
    )
    cells[9] = CellDef(
        widget=Text(text="STATUS", color=SECONDARY_TEXT, font_sizes=(11, 10, 9), valign="bottom"),
        key_num=9,
    )

    # --- Row 2: Values (cols 1-3) ---
    cells[2] = CellDef(
        widget=Text(text=name, color=_SETUP_COLOR, font_sizes=(14, 12, 10), valign="top"),
        key_num=2,
    )
    cells[3] = CellDef(
        widget=Text(text=code, color=_SETUP_COLOR, font_sizes=(16, 14, 12), valign="top"),
        key_num=3,
    )
    status_color = (102, 204, 102) if status == "Paired!" else _SETUP_COLOR
    cells[4] = CellDef(
        widget=Text(text=status, color=status_color, font_sizes=(14, 12, 10), valign="top"),
        key_num=4,
    )

    # --- BACK button ---
    cells[1] = CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="BACK", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="back",
    )

    # --- pre_render: paste QR code into the R1C0 area (key 6 zone) ---
    # Capture the QR image for the closure
    qr_img = qr_image

    def _pre_render(img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        # Target area: column 0, spanning rows 1 and 2
        x = VIS_COL_X[0]
        y = VIS_ROW_Y[1]
        w = VIS_COL_W[0]
        h = VIS_ROW_H[1]  # Just row 1 height — fits the QR

        # Scale QR to fit the cell, maintaining aspect ratio
        qr_w, qr_h = qr_img.size
        scale = min(w / qr_w, h / qr_h)
        new_w = int(qr_w * scale)
        new_h = int(qr_h * scale)
        scaled = qr_img.resize((new_w, new_h), Image.NEAREST)

        # Center in the cell
        px = x + (w - new_w) // 2
        py = y + (h - new_h) // 2
        img.paste(scaled, (px, py))

        # Draw accent lines between label and value rows (same as data_page)
        accent = darken(_SETUP_COLOR, 0.2)
        for i in range(3):
            col_idx = i + 1
            cx = VIS_COL_X[col_idx] + VIS_COL_W[col_idx] // 2
            y_start = VIS_ROW_Y[1] + VIS_ROW_H[1]
            y_end = VIS_ROW_Y[2]
            draw.line([(cx, y_start), (cx, y_end)], fill=accent, width=1)

    return ScreenDef(name="setup_qr", cells=cells, pre_render=_pre_render)
