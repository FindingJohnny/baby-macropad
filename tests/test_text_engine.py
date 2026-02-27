"""Tests for the centralized text engine."""

from PIL import Image, ImageDraw

from baby_macropad.ui.framework.text_engine import (
    draw_centered_text,
    fit_text,
    get_font,
)
from baby_macropad.ui.framework.primitives import ICON_LABELS, VIS_COL_W, VIS_ROW_H


class TestGetFont:
    def test_returns_font_object(self):
        font = get_font(14)
        assert font is not None

    def test_various_sizes(self):
        for size in (8, 11, 14, 18, 24):
            font = get_font(size)
            assert font is not None

    def test_bold_and_regular(self):
        bold = get_font(14, bold=True)
        regular = get_font(14, bold=False)
        assert bold is not None
        assert regular is not None

    def test_caching_returns_same_object(self):
        a = get_font(12, bold=True)
        b = get_font(12, bold=True)
        assert a is b


class TestFitText:
    def _make_draw(self):
        img = Image.new("RGB", (200, 100))
        return ImageDraw.Draw(img)

    def test_text_fits_within_bounds(self):
        draw = self._make_draw()
        font, text, w, h = fit_text(draw, "OK", max_width=100, max_height=50)
        assert w <= 100
        assert h <= 50
        assert text == "OK"

    def test_truncates_long_text(self):
        draw = self._make_draw()
        long_text = "A" * 50
        font, text, w, h = fit_text(draw, long_text, max_width=40, max_height=50)
        assert w <= 40
        assert text.endswith("\u2026")

    def test_empty_string(self):
        draw = self._make_draw()
        font, text, w, h = fit_text(draw, "", max_width=100, max_height=50)
        assert text == ""
        assert w == 0

    def test_custom_font_sizes(self):
        draw = self._make_draw()
        font, text, w, h = fit_text(
            draw, "Hello", max_width=200, max_height=100, font_sizes=(24, 18, 12)
        )
        assert text == "Hello"

    def test_regular_weight(self):
        draw = self._make_draw()
        font, text, w, h = fit_text(draw, "Test", max_width=100, max_height=50, bold=False)
        assert text == "Test"


class TestDrawCenteredText:
    def test_does_not_raise(self):
        img = Image.new("RGB", (200, 100))
        draw = ImageDraw.Draw(img)
        font = get_font(14)
        # Should not raise
        draw_centered_text(draw, "Hello", x=0, y=0, w=200, h=100, fill=(255, 255, 255), font=font)

    def test_with_empty_string(self):
        img = Image.new("RGB", (200, 100))
        draw = ImageDraw.Draw(img)
        font = get_font(14)
        draw_centered_text(draw, "", x=0, y=0, w=200, h=100, fill=(255, 255, 255), font=font)


class TestIconLabelsFit:
    """All known icon labels should fit within a single cell's visible area."""

    def test_all_labels_fit_in_cell(self):
        draw = ImageDraw.Draw(Image.new("RGB", (100, 100)))
        max_w = min(VIS_COL_W)  # 72
        max_h = min(VIS_ROW_H)  # 60
        for name, label in ICON_LABELS.items():
            font, text, w, h = fit_text(draw, label, max_width=max_w, max_height=max_h)
            assert w <= max_w, f"Label '{label}' for '{name}' too wide: {w} > {max_w}"
            assert h <= max_h, f"Label '{label}' for '{name}' too tall: {h} > {max_h}"
            # Labels should not be truncated
            assert text == label, f"Label '{label}' for '{name}' was truncated to '{text}'"
