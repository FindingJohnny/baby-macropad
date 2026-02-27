"""Widget building blocks for macropad screen cells.

Each widget implements render(img, draw, rect) -> None.
Widgets are stateless — constructed with data, rendered immutably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from PIL import Image, ImageDraw

from .icon_cache import load_and_tint, load_composite
from .primitives import CARD_MARGIN, CARD_RADIUS, ICON_ASSETS, Rect, darken
from .text_engine import draw_centered_text, fit_text, get_font


@runtime_checkable
class Widget(Protocol):
    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect) -> None: ...


@dataclass
class Card:
    """Rounded rectangle background card."""

    fill: tuple[int, int, int] | None = None
    outline: tuple[int, int, int] | None = None
    radius: int = CARD_RADIUS
    child: Widget | None = None

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect) -> None:
        x = rect.x + CARD_MARGIN
        y = rect.y + CARD_MARGIN
        w = rect.w - CARD_MARGIN * 2
        h = rect.h - CARD_MARGIN * 2
        draw.rounded_rectangle(
            [x, y, x + w, y + h],
            radius=self.radius,
            fill=self.fill,
            outline=self.outline,
            width=2 if self.outline else 0,
        )
        if self.child is not None:
            self.child.render(img, draw, Rect(x, y, w, h))


@dataclass
class Text:
    """Single-line text centered in the cell with auto font sizing."""

    text: str
    color: tuple[int, int, int] = (255, 255, 255)
    font_sizes: tuple[int, ...] = (14, 12, 10)
    bold: bool = True

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect) -> None:
        font, display_text, tw, th = fit_text(
            draw, self.text, rect.w, rect.h, self.font_sizes, bold=self.bold
        )
        draw_centered_text(draw, display_text, rect.x, rect.y, rect.w, rect.h, self.color, font)


@dataclass
class TwoLineText:
    """Title + subtitle stacked vertically, centered as a group."""

    line1: str
    line2: str
    color1: tuple[int, int, int] = (142, 142, 147)
    color2: tuple[int, int, int] = (200, 200, 200)
    font_size1: int = 9
    font_size2: int = 14

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect) -> None:
        font1 = get_font(self.font_size1, bold=True)
        font2 = get_font(self.font_size2, bold=True)
        tb1 = draw.textbbox((0, 0), self.line1, font=font1)
        tb2 = draw.textbbox((0, 0), self.line2, font=font2)
        h1 = tb1[3] - tb1[1]
        h2 = tb2[3] - tb2[1]
        gap = 3
        total_h = h1 + gap + h2
        by = rect.y + (rect.h - total_h) // 2

        w1 = tb1[2] - tb1[0]
        draw.text(
            (rect.x + (rect.w - w1) // 2, by), self.line1, fill=self.color1, font=font1
        )
        w2 = tb2[2] - tb2[0]
        draw.text(
            (rect.x + (rect.w - w2) // 2, by + h1 + gap), self.line2, fill=self.color2, font=font2
        )


@dataclass
class Icon:
    """Tinted Tabler icon centered in the cell."""

    asset_name: str
    color: tuple[int, int, int] = (255, 255, 255)
    size: int = 36

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect) -> None:
        # Resolve through ICON_ASSETS mapping
        asset = ICON_ASSETS.get(self.asset_name, self.asset_name)
        tinted = None
        if isinstance(asset, tuple):
            tinted = load_composite(asset[0], asset[1], self.color, self.size)
        else:
            tinted = load_and_tint(asset, self.color, self.size)
        if tinted:
            ix = rect.x + (rect.w - self.size) // 2
            iy = rect.y + (rect.h - self.size) // 2
            img.paste(tinted, (ix, iy), tinted)


@dataclass
class IconLabel:
    """Icon + text label stacked vertically (home grid button style).

    Falls back to 4-char text abbreviation if icon asset is missing.
    """

    icon_name: str
    label: str
    color: tuple[int, int, int] = (200, 200, 200)
    icon_size: int = 36
    badge: str | None = None

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect) -> None:
        label_font = get_font(11, bold=True)
        badge_font = get_font(8, bold=True)
        fallback_font = get_font(18, bold=True)

        label_height = 13
        icon_label_gap = 3
        content_height = self.icon_size + icon_label_gap + label_height

        top_offset = (rect.h - content_height) // 2

        # Try to load icon
        asset = ICON_ASSETS.get(self.icon_name, self.icon_name)
        icon_drawn = False
        if isinstance(asset, tuple):
            tinted = load_composite(asset[0], asset[1], self.color, self.icon_size)
            if tinted:
                ix = rect.x + (rect.w - self.icon_size) // 2
                iy = rect.y + top_offset
                img.paste(tinted, (ix, iy), tinted)
                icon_drawn = True
        elif asset:
            tinted = load_and_tint(asset, self.color, self.icon_size)
            if tinted:
                ix = rect.x + (rect.w - self.icon_size) // 2
                iy = rect.y + top_offset
                img.paste(tinted, (ix, iy), tinted)
                icon_drawn = True

        if not icon_drawn:
            # Fallback: draw text centered in icon area
            text = self.label[:4].upper()
            bbox = draw.textbbox((0, 0), text, font=fallback_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = rect.x + (rect.w - tw) // 2
            ty = rect.y + top_offset + (self.icon_size - th) // 2
            draw.text((tx, ty), text, fill=self.color, font=fallback_font)

        # Draw label below icon
        from .primitives import ICON_LABELS

        display_label = ICON_LABELS.get(self.icon_name, self.label[:6].upper())
        bbox = draw.textbbox((0, 0), display_label, font=label_font)
        lw = bbox[2] - bbox[0]
        lx = rect.x + (rect.w - lw) // 2
        ly = rect.y + top_offset + self.icon_size + icon_label_gap
        draw.text((lx, ly), display_label, fill=self.color, font=label_font)

        # Draw badge if present
        if self.badge:
            bbox = draw.textbbox((0, 0), self.badge, font=badge_font)
            bw = bbox[2] - bbox[0]
            bx = rect.x + (rect.w - bw) // 2
            by = ly + label_height + 1
            draw.text((bx, by), self.badge, fill=self.color, font=badge_font)


@dataclass
class Spacer:
    """Empty transparent cell — no-op render."""

    def render(self, img: Image.Image, draw: ImageDraw.ImageDraw, rect: Rect) -> None:
        pass
