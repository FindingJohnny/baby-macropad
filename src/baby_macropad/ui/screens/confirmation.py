"""Confirmation screen factory — 5 cycleable layout variants.

Each layout variant receives the same data and produces a ScreenDef.
The active layout is selected by the ``confirmation_layout`` setting.

Grid reminder (after key remap):
  Row 0 (top):    keys 11  12  13  14  15
  Row 1 (mid):    keys  6   7   8   9  10
  Row 2 (bot):    keys  1   2   3   4   5
"""

from __future__ import annotations

from ..framework.primitives import BACK_BUTTON_BG, BG_COLOR, SECONDARY_TEXT, darken
from ..framework.screen import CellDef, ScreenDef
from ..framework.widgets import Card, Icon, Spacer, Text, TwoLineText

WHITE = (255, 255, 255)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _label_widget(action_label: str) -> Text | TwoLineText:
    """Build a label widget handling multi-line labels."""
    if "\n" in action_label:
        parts = action_label.split("\n", 1)
        return TwoLineText(
            line1=parts[0], line2=parts[1],
            color1=WHITE, color2=WHITE,
            font_sizes1=(14, 12, 10), font_sizes2=(14, 12, 10),
        )
    return Text(text=action_label, color=WHITE, font_sizes=(18, 14, 12))


def _undo_cell(resource_id: str | None) -> CellDef | None:
    if not resource_id:
        return None
    return CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="UNDO", color=SECONDARY_TEXT, font_sizes=(12, 10)),
        ),
        key_num=1,
        on_press="undo",
    )


def _done_cell(key: int = 5) -> CellDef:
    return CellDef(
        widget=Card(
            fill=BACK_BUTTON_BG,
            child=Text(text="DONE", color=WHITE, font_sizes=(12, 10)),
        ),
        key_num=key,
        on_press="done",
    )


def _context_cell(context_line: str, key: int = 9) -> CellDef | None:
    if not context_line:
        return None
    return CellDef(
        widget=Text(text=context_line, color=SECONDARY_TEXT, font_sizes=(11, 10, 9)),
        key_num=key,
    )


# ---------------------------------------------------------------------------
# Layout 1: "banner" — color header top row + label/context middle + UNDO/DONE
# ---------------------------------------------------------------------------

def _build_banner(
    label: str, context: str, color: tuple[int, int, int],
    icon: str, resource_id: str | None,
) -> ScreenDef:
    cells: dict[int, CellDef] = {}

    # Top row: full category color with checkmark center
    for key in (11, 12, 14, 15):
        cells[key] = CellDef(
            widget=Card(fill=color, child=Spacer()), key_num=key,
        )
    cells[13] = CellDef(
        widget=Card(fill=color, child=Icon(asset_name="check", color=WHITE, size=36)),
        key_num=13,
    )

    # Middle: label + context
    cells[8] = CellDef(widget=_label_widget(label), key_num=8)
    ctx = _context_cell(context)
    if ctx:
        cells[ctx.key_num] = ctx

    # Bottom: UNDO + DONE
    undo = _undo_cell(resource_id)
    if undo:
        cells[undo.key_num] = undo
    cells[5] = _done_cell()

    return ScreenDef(name="confirmation", cells=cells)


# ---------------------------------------------------------------------------
# Layout 2: "center_stage" — large action icon at center, label below
# ---------------------------------------------------------------------------

def _build_center_stage(
    label: str, context: str, color: tuple[int, int, int],
    icon: str, resource_id: str | None,
) -> ScreenDef:
    cells: dict[int, CellDef] = {}

    # Top row: thin accent line via colored outline cards
    for key in (11, 12, 13, 14, 15):
        cells[key] = CellDef(
            widget=Card(fill=darken(color, 0.15), outline=darken(color, 0.4), child=Spacer()),
            key_num=key,
        )

    # Center: large action icon with check overlay
    cells[8] = CellDef(
        widget=Card(
            fill=darken(color, 0.2),
            outline=color,
            child=Icon(asset_name=icon or "check", color=color, size=36),
        ),
        key_num=8,
    )

    # Flanking: label left, context right
    cells[7] = CellDef(widget=_label_widget(label), key_num=7)
    ctx = _context_cell(context, key=9)
    if ctx:
        cells[ctx.key_num] = ctx

    # Bottom: UNDO + DONE
    undo = _undo_cell(resource_id)
    if undo:
        cells[undo.key_num] = undo
    cells[5] = _done_cell()

    return ScreenDef(name="confirmation", cells=cells)


# ---------------------------------------------------------------------------
# Layout 3: "full_icon" — full-screen category color bg, big icon + label
# ---------------------------------------------------------------------------

def _build_full_icon(
    label: str, context: str, color: tuple[int, int, int],
    icon: str, resource_id: str | None,
) -> ScreenDef:
    cells: dict[int, CellDef] = {}

    # All cells get category color background
    for key in (11, 12, 14, 15, 6, 7, 9, 10, 2, 3, 4):
        cells[key] = CellDef(
            widget=Card(fill=color, child=Spacer()), key_num=key,
        )

    # Center top: action icon (large)
    cells[13] = CellDef(
        widget=Card(
            fill=color,
            child=Icon(asset_name=icon or "check", color=WHITE, size=36),
        ),
        key_num=13,
    )

    # Center middle: label
    cells[8] = CellDef(
        widget=Card(
            fill=color,
            child=Text(text=label.replace("\n", " "), color=WHITE, font_sizes=(14, 12, 10)),
        ),
        key_num=8,
    )

    # Bottom corners: UNDO + DONE (dark cards on color bg for contrast)
    undo = _undo_cell(resource_id)
    if undo:
        cells[undo.key_num] = undo
    cells[5] = _done_cell()

    return ScreenDef(name="confirmation", cells=cells, background_color=color)


# ---------------------------------------------------------------------------
# Layout 4: "split" — left panel (cols 0-1) colored with icon, right panel text
# ---------------------------------------------------------------------------

def _build_split(
    label: str, context: str, color: tuple[int, int, int],
    icon: str, resource_id: str | None,
) -> ScreenDef:
    cells: dict[int, CellDef] = {}

    # Left column (col 0): category color fill
    for key in (11, 6, 1):
        cells[key] = CellDef(
            widget=Card(fill=color, child=Spacer()), key_num=key,
        )

    # Left col 1: icon at top, check at bottom
    cells[12] = CellDef(
        widget=Card(
            fill=color,
            child=Icon(asset_name=icon or "check", color=WHITE, size=36),
        ),
        key_num=12,
    )
    cells[7] = CellDef(
        widget=Card(fill=color, child=Icon(asset_name="check", color=WHITE, size=24)),
        key_num=7,
    )
    cells[2] = CellDef(
        widget=Card(fill=color, child=Spacer()), key_num=2,
    )

    # Right side: label at key 14 (top-right area), context at 9
    cells[14] = CellDef(widget=_label_widget(label), key_num=14)
    ctx = _context_cell(context, key=9)
    if ctx:
        cells[ctx.key_num] = ctx

    # DONE at bottom-right
    cells[5] = _done_cell()

    # UNDO at bottom-center-right if available
    undo = _undo_cell(resource_id)
    if undo:
        undo.key_num = 4
        cells[4] = undo

    return ScreenDef(name="confirmation", cells=cells)


# ---------------------------------------------------------------------------
# Layout 5: "minimal" — clean dark, just essentials
# ---------------------------------------------------------------------------

def _build_minimal(
    label: str, context: str, color: tuple[int, int, int],
    icon: str, resource_id: str | None,
) -> ScreenDef:
    cells: dict[int, CellDef] = {}

    # Top row: only center checkmark, small colored accent
    cells[13] = CellDef(
        widget=Icon(asset_name="check", color=color, size=28),
        key_num=13,
    )

    # Middle: label centered
    cells[8] = CellDef(widget=_label_widget(label), key_num=8)

    # Context below label if present
    ctx = _context_cell(context, key=3)
    if ctx:
        cells[ctx.key_num] = ctx

    # DONE at bottom-right, small
    cells[5] = _done_cell()

    # UNDO at bottom-left if available
    undo = _undo_cell(resource_id)
    if undo:
        cells[undo.key_num] = undo

    return ScreenDef(name="confirmation", cells=cells)


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

_LAYOUTS = {
    "banner": _build_banner,
    "center_stage": _build_center_stage,
    "full_icon": _build_full_icon,
    "split": _build_split,
    "minimal": _build_minimal,
}


def build_confirmation_screen(
    action_label: str,
    context_line: str,
    category_color: tuple[int, int, int],
    resource_id: str | None = None,
    icon: str = "",
    layout: str = "banner",
) -> ScreenDef:
    """Build a confirmation screen using the selected layout variant."""
    builder = _LAYOUTS.get(layout, _build_banner)
    return builder(action_label, context_line, category_color, icon, resource_id)
