"""Tests for detail, confirmation, and sleep mode renderers."""

import io

from PIL import Image

from baby_macropad.ui.detail import render_detail_screen
from baby_macropad.ui.confirmation import render_confirmation
from baby_macropad.ui.sleep import render_sleep_mode


class TestDetailScreen:
    def test_returns_valid_jpeg(self):
        data = render_detail_screen(
            title="LEFT BREAST",
            options=[
                {"label": "LEFT", "key_num": 11, "selected": True},
                {"label": "RIGHT", "key_num": 12, "selected": False},
            ],
            timer_seconds=45,
            category_color=(102, 204, 102),
        )
        assert isinstance(data, bytes)
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)
        assert img.format == "JPEG"

    def test_no_options(self):
        data = render_detail_screen(
            title="BOTTLE",
            options=[],
            timer_seconds=30,
            category_color=(102, 204, 102),
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)

    def test_single_option_selected(self):
        data = render_detail_screen(
            title="POOP",
            options=[{"label": "NORMAL", "key_num": 11, "selected": True}],
            timer_seconds=60,
            category_color=(204, 170, 68),
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)

    def test_four_options(self):
        data = render_detail_screen(
            title="DIAPER",
            options=[
                {"label": "PEE", "key_num": 11, "selected": False},
                {"label": "POOP", "key_num": 12, "selected": True},
                {"label": "BOTH", "key_num": 13, "selected": False},
                {"label": "DRY", "key_num": 14, "selected": False},
            ],
            timer_seconds=10,
            category_color=(204, 170, 68),
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)


class TestConfirmationScreen:
    def test_returns_valid_jpeg(self):
        data = render_confirmation(
            action_label="Left breast logged",
            context_line="Next: Right breast",
            icon_name="bottle",
            category_color=(102, 204, 102),
            celebration_style="color_fill",
            column_index=0,
        )
        assert isinstance(data, bytes)
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)
        assert img.format == "JPEG"

    def test_no_celebration(self):
        data = render_confirmation(
            action_label="Pee diaper logged",
            context_line="",
            icon_name="diaper",
            category_color=(204, 170, 68),
            celebration_style="none",
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)

    def test_missing_icon_graceful(self):
        """Should render without crashing even if icon asset is missing."""
        data = render_confirmation(
            action_label="Note saved",
            context_line="",
            icon_name="nonexistent_icon",
            category_color=(153, 153, 153),
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)

    def test_column_index_bounds(self):
        """Column index 4 (rightmost) should work."""
        data = render_confirmation(
            action_label="Sleep started",
            context_line="Tap to wake",
            icon_name="moon",
            category_color=(102, 153, 204),
            column_index=4,
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)


class TestSleepMode:
    def test_returns_valid_jpeg(self):
        data = render_sleep_mode(
            elapsed_minutes=45,
            start_time_str="10:14 PM",
        )
        assert isinstance(data, bytes)
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)
        assert img.format == "JPEG"

    def test_hours_format(self):
        data = render_sleep_mode(
            elapsed_minutes=125,
            start_time_str="8:30 PM",
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)

    def test_zero_minutes(self):
        data = render_sleep_mode(
            elapsed_minutes=0,
            start_time_str="11:00 PM",
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)

    def test_long_duration(self):
        data = render_sleep_mode(
            elapsed_minutes=600,
            start_time_str="2:00 AM",
        )
        img = Image.open(io.BytesIO(data))
        assert img.size == (480, 272)
