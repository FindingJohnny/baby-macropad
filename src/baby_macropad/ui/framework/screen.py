"""Screen definition and renderer.

A ScreenDef describes a screen as a data structure. The ScreenRenderer
turns it into 480x272 JPEG bytes. Screen factories produce ScreenDefs
from runtime data — they never render pixels directly.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from .primitives import (
    BG_COLOR,
    SCREEN_H,
    SCREEN_W,
    VIS_COL_W,
    VIS_COL_X,
    VIS_ROW_H,
    VIS_ROW_Y,
    Rect,
    key_to_grid,
)
from .widgets import Widget


@dataclass
class CellDef:
    """A single cell on the screen grid."""

    widget: Widget
    key_num: int
    on_press: str | None = None
    span_cols: int = 1


@dataclass
class ScreenDef:
    """Declarative description of a full screen."""

    name: str
    cells: dict[int, CellDef]
    background_color: tuple[int, int, int] = BG_COLOR
    pre_render: Callable[[Image.Image, ImageDraw.ImageDraw], None] | None = None


class ScreenRenderer:
    """Renders a ScreenDef to 480x272 JPEG bytes."""

    def render(self, screen: ScreenDef) -> bytes:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), screen.background_color)
        draw = ImageDraw.Draw(img)

        # Pre-render callback for non-cell content
        if screen.pre_render is not None:
            screen.pre_render(img, draw)

        # Render each cell
        for key_num, cell in screen.cells.items():
            pos = key_to_grid(cell.key_num)
            if pos is None:
                continue
            col, row = pos

            if cell.span_cols > 1:
                # Span across multiple columns including gap pixels
                end_col = min(col + cell.span_cols - 1, 4)
                x = VIS_COL_X[col]
                w = VIS_COL_X[end_col] + VIS_COL_W[end_col] - x
                rect = Rect(x, VIS_ROW_Y[row], w, VIS_ROW_H[row])
            else:
                rect = Rect(VIS_COL_X[col], VIS_ROW_Y[row], VIS_COL_W[col], VIS_ROW_H[row])

            cell.widget.render(img, draw, rect)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
