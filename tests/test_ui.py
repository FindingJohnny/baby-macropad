"""Tests for icon generation and dashboard rendering."""

from pathlib import Path

import pytest
from PIL import Image

from baby_macropad.ui.icons import ICON_COLORS, ICON_LABELS, generate_all_icons, generate_icon
from baby_macropad.ui.dashboard import render_dashboard, save_dashboard


class TestIconGeneration:
    def test_generate_icon_returns_correct_size(self):
        img = generate_icon("breast_left")
        assert img.size == (64, 64)
        assert img.mode == "RGB"

    def test_generate_icon_for_all_known_types(self):
        for icon_name in ICON_LABELS:
            img = generate_icon(icon_name)
            assert img.size == (64, 64), f"Failed for {icon_name}"

    def test_generate_icon_unknown_name(self):
        img = generate_icon("nonexistent")
        assert img.size == (64, 64)

    def test_generate_icon_custom_label(self):
        img = generate_icon("breast_left", label="LEFT")
        assert img.size == (64, 64)

    def test_generate_all_icons(self, tmp_path: Path):
        class FakeButton:
            def __init__(self, icon: str, label: str):
                self.icon = icon
                self.label = label

        buttons = {
            1: FakeButton("breast_left", "Breast L"),
            2: FakeButton("breast_right", "Breast R"),
            9: FakeButton("sleep", "Sleep"),
        }
        paths = generate_all_icons(buttons, tmp_path / "icons")
        assert len(paths) == 3
        for key_num, path in paths.items():
            assert path.exists()
            img = Image.open(path)
            assert img.size == (64, 64)

    def test_generate_all_icons_skips_empty_icon(self, tmp_path: Path):
        class FakeButton:
            def __init__(self, icon: str, label: str):
                self.icon = icon
                self.label = label

        buttons = {
            1: FakeButton("", "No Icon"),
        }
        paths = generate_all_icons(buttons, tmp_path / "icons")
        assert len(paths) == 0


class TestDashboardRendering:
    def test_render_empty_dashboard(self):
        img = render_dashboard(dashboard_data=None, connected=True)
        assert img.size == (480, 272)
        assert img.mode == "RGB"

    def test_render_dashboard_with_data(self):
        data = {
            "active_sleep": {"id": "s1", "start_time": "2026-02-26T01:00:00Z"},
            "last_feeding": {
                "id": "f1",
                "type": "breast",
                "started_side": "left",
                "created_at": "2026-02-26T00:30:00Z",
            },
            "last_diaper": {
                "id": "d1",
                "type": "pee",
                "created_at": "2026-02-25T23:00:00Z",
            },
            "last_sleep": None,
            "suggested_side": "right",
            "today_counts": {"feedings": 6, "pee": 4, "poop": 2, "sleep_hours": 8.5},
        }
        img = render_dashboard(dashboard_data=data, connected=True)
        assert img.size == (480, 272)

    def test_render_dashboard_awake_state(self):
        data = {
            "active_sleep": None,
            "last_feeding": None,
            "last_diaper": None,
            "last_sleep": {"id": "s0", "end_time": "2026-02-26T05:00:00Z"},
            "suggested_side": None,
            "today_counts": {},
        }
        img = render_dashboard(dashboard_data=data, connected=True)
        assert img.size == (480, 272)

    def test_render_dashboard_offline(self):
        img = render_dashboard(dashboard_data=None, connected=False, queued_count=5)
        assert img.size == (480, 272)

    def test_save_dashboard(self, tmp_path: Path):
        path = save_dashboard(
            output_path=tmp_path / "dash" / "dashboard.jpg",
            dashboard_data=None,
            connected=True,
        )
        assert path.exists()
        img = Image.open(path)
        assert img.size == (480, 272)

    def test_render_dashboard_no_counts(self):
        data = {
            "active_sleep": None,
            "last_feeding": None,
            "last_diaper": None,
            "last_sleep": None,
            "suggested_side": None,
            "today_counts": {},
        }
        img = render_dashboard(dashboard_data=data, connected=True)
        assert img.size == (480, 272)
