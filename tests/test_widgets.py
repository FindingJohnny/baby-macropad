"""Tests for the widget system."""

from PIL import Image, ImageDraw

from baby_macropad.ui.framework.primitives import Rect
from baby_macropad.ui.framework.widgets import (
    Card,
    Icon,
    IconLabel,
    Spacer,
    Text,
    TwoLineText,
    Widget,
)


def _make_img_draw():
    img = Image.new("RGB", (480, 272), (28, 28, 30))
    draw = ImageDraw.Draw(img)
    return img, draw


def _cell_rect():
    return Rect(x=11, y=10, w=72, h=60)


class TestWidgetProtocol:
    def test_card_satisfies_protocol(self):
        assert isinstance(Card(), Widget)

    def test_text_satisfies_protocol(self):
        assert isinstance(Text(text="Hi"), Widget)

    def test_two_line_text_satisfies_protocol(self):
        assert isinstance(TwoLineText(line1="A", line2="B"), Widget)

    def test_icon_satisfies_protocol(self):
        assert isinstance(Icon(asset_name="moon"), Widget)

    def test_icon_label_satisfies_protocol(self):
        assert isinstance(IconLabel(icon_name="moon", label="SLEEP"), Widget)

    def test_spacer_satisfies_protocol(self):
        assert isinstance(Spacer(), Widget)


class TestCard:
    def test_renders_without_error(self):
        img, draw = _make_img_draw()
        card = Card(fill=(50, 50, 50))
        card.render(img, draw, _cell_rect())

    def test_with_outline(self):
        img, draw = _make_img_draw()
        card = Card(fill=(50, 50, 50), outline=(100, 100, 100))
        card.render(img, draw, _cell_rect())

    def test_with_child_widget(self):
        img, draw = _make_img_draw()
        child = Text(text="Hello", color=(255, 255, 255))
        card = Card(fill=(50, 50, 50), child=child)
        card.render(img, draw, _cell_rect())
        # Both card and child should render without error

    def test_no_fill_no_outline(self):
        img, draw = _make_img_draw()
        card = Card()
        card.render(img, draw, _cell_rect())


class TestText:
    def test_renders_without_error(self):
        img, draw = _make_img_draw()
        text = Text(text="OK", color=(255, 255, 255))
        text.render(img, draw, _cell_rect())

    def test_long_string_truncates(self):
        img, draw = _make_img_draw()
        text = Text(text="A" * 50, color=(255, 255, 255))
        # Should not raise even with very long text
        text.render(img, draw, _cell_rect())

    def test_empty_string(self):
        img, draw = _make_img_draw()
        text = Text(text="", color=(255, 255, 255))
        text.render(img, draw, _cell_rect())

    def test_custom_font_sizes(self):
        img, draw = _make_img_draw()
        text = Text(text="Hi", font_sizes=(20, 16, 12))
        text.render(img, draw, _cell_rect())


class TestTwoLineText:
    def test_renders_without_error(self):
        img, draw = _make_img_draw()
        widget = TwoLineText(line1="Timer", line2="7s")
        widget.render(img, draw, _cell_rect())

    def test_custom_colors(self):
        img, draw = _make_img_draw()
        widget = TwoLineText(
            line1="Label",
            line2="Value",
            color1=(100, 100, 100),
            color2=(200, 200, 200),
        )
        widget.render(img, draw, _cell_rect())


class TestIcon:
    def test_renders_without_error(self):
        img, draw = _make_img_draw()
        icon = Icon(asset_name="moon", color=(102, 153, 204))
        icon.render(img, draw, _cell_rect())

    def test_missing_asset_graceful(self):
        img, draw = _make_img_draw()
        icon = Icon(asset_name="nonexistent_icon_xyz")
        # Should not raise
        icon.render(img, draw, _cell_rect())

    def test_composite_icon(self):
        img, draw = _make_img_draw()
        # diaper_both maps to a tuple in ICON_ASSETS
        icon = Icon(asset_name="diaper_both", color=(204, 170, 68))
        icon.render(img, draw, _cell_rect())


class TestIconLabel:
    def test_renders_without_error(self):
        img, draw = _make_img_draw()
        widget = IconLabel(icon_name="moon", label="SLEEP", color=(102, 153, 204))
        widget.render(img, draw, _cell_rect())

    def test_missing_icon_falls_back_to_text(self):
        img, draw = _make_img_draw()
        widget = IconLabel(icon_name="nonexistent_xyz", label="TEST", color=(200, 200, 200))
        # Should fall back to text, not raise
        widget.render(img, draw, _cell_rect())

    def test_with_badge(self):
        img, draw = _make_img_draw()
        widget = IconLabel(
            icon_name="breast_left",
            label="LEFT",
            color=(102, 204, 102),
            badge="\u25b6 NEXT",
        )
        widget.render(img, draw, _cell_rect())

    def test_composite_icon_name(self):
        img, draw = _make_img_draw()
        widget = IconLabel(icon_name="diaper_both", label="BOTH", color=(204, 170, 68))
        widget.render(img, draw, _cell_rect())


class TestSpacer:
    def test_renders_without_error(self):
        img, draw = _make_img_draw()
        spacer = Spacer()
        spacer.render(img, draw, _cell_rect())

    def test_is_noop(self):
        img, draw = _make_img_draw()
        # Capture pixels before and after
        before = img.copy()
        spacer = Spacer()
        spacer.render(img, draw, _cell_rect())
        assert img.tobytes() == before.tobytes()
