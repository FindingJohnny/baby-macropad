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

    def __init__(self) -> None:
        self._cached_canvas: Image.Image | None = None

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

        self._cached_canvas = img.copy()

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65)
        return buf.getvalue()

    def render_press_feedback(
        self, key_num: int, color: tuple[int, int, int], alpha: float = 0.35,
    ) -> bytes | None:
        """Render a press highlight by blending color onto the cached canvas.

        Returns JPEG bytes, or None if no cached canvas is available.
        Skips the full widget tree — just paste + encode.
        """
        if self._cached_canvas is None:
            return None
        pos = key_to_grid(key_num)
        if pos is None:
            return None
        col, row = pos
        x, y = VIS_COL_X[col], VIS_ROW_Y[row]
        w, h = VIS_COL_W[col], VIS_ROW_H[row]

        img = self._cached_canvas.copy()
        region = img.crop((x, y, x + w, y + h))
        overlay = Image.new("RGB", (w, h), color)
        blended = Image.blend(region, overlay, alpha)
        img.paste(blended, (x, y))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50)
        return buf.getvalue()
