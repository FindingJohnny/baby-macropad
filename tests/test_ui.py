"""Tests for icon grid rendering and dashboard rendering."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from baby_macropad.ui.icons import (
    ICON_COLORS,
    ICON_LABELS,
    get_key_grid_bytes,
    render_key_grid,
    save_key_grid,
)
from baby_macropad.ui.dashboard import render_dashboard, save_dashboard


class TestKeyGridRendering:
    def _make_button(self, icon: str, label: str):
        class FakeButton:
            def __init__(self, icon: str, label: str):
                self.icon = icon
                self.label = label
        return FakeButton(icon, label)

    def test_render_empty_grid(self):
        img = render_key_grid({})
        assert img.size == (480, 272)
        assert img.mode == "RGB"

    def test_render_grid_with_buttons(self):
        buttons = {
            11: self._make_button("breast_left", "LEFT"),
            6: self._make_button("breast_right", "RIGHT"),
            1: self._make_button("bottle", "BOTTLE"),
        }
        img = render_key_grid(buttons)
        assert img.size == (480, 272)

    def test_get_key_grid_bytes_returns_jpeg(self):
        buttons = {12: self._make_button("diaper_pee", "PEE")}
        data = get_key_grid_bytes(buttons)
        assert isinstance(data, bytes)
        assert data[:2] == b'\xff\xd8'  # JPEG magic bytes
        img = Image.open(BytesIO(data))
        assert img.size == (480, 272)

    def test_save_key_grid(self, tmp_path: Path):
        buttons = {13: self._make_button("sleep", "SLEEP")}
        path = save_key_grid(buttons, tmp_path / "grid.jpg")
        assert path.exists()
        img = Image.open(path)
        assert img.size == (480, 272)

    def test_render_all_icon_types(self):
        """Verify all registered icon names render without error."""
        for i, icon_name in enumerate(ICON_LABELS):
            buttons = {11: self._make_button(icon_name, ICON_LABELS[icon_name])}
            img = render_key_grid(buttons)
            assert img.size == (480, 272), f"Failed for {icon_name}"

    def test_render_with_runtime_state(self):
        buttons = {13: self._make_button("sleep", "SLEEP")}
        runtime_state = {13: "active:1h 30m"}
        img = render_key_grid(buttons, runtime_state=runtime_state)
        assert img.size == (480, 272)

    def test_render_with_suggested_breast(self):
        buttons = {11: self._make_button("breast_left", "LEFT")}
        runtime_state = {11: "suggested"}
        img = render_key_grid(buttons, runtime_state=runtime_state)
        assert img.size == (480, 272)

    def test_composite_icon_diaper_both(self):
        buttons = {2: self._make_button("diaper_both", "BOTH")}
        img = render_key_grid(buttons)
        assert img.size == (480, 272)


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
