"""Tests for screen factories and ScreenRenderer."""

import io

from PIL import Image

from baby_macropad.settings import SettingsModel
from baby_macropad.ui.framework.screen import ScreenRenderer
from baby_macropad.ui.screens.home import build_home_grid
from baby_macropad.ui.screens.detail import build_detail_screen
from baby_macropad.ui.screens.confirmation import build_confirmation_screen
from baby_macropad.ui.screens.selection import build_selection_screen
from baby_macropad.ui.screens.settings_screen import build_settings_screen
from baby_macropad.ui.screens.sleep_screen import build_sleep_screen
from baby_macropad.ui.screens.dashboard_screen import build_dashboard_screen


def _validate_jpeg(data: bytes) -> Image.Image:
    """Assert data is valid 480x272 JPEG and return the image."""
    assert isinstance(data, bytes)
    img = Image.open(io.BytesIO(data))
    assert img.size == (480, 272)
    assert img.format == "JPEG"
    return img


def _make_buttons(count: int = 15) -> dict[int, dict]:
    """Generate button configs for keys 1-count."""
    icons = [
        "breast_left", "breast_right", "bottle", "pump", "settings",
        "diaper_pee", "diaper_poop", "diaper_both", "note", "sleep",
        "breast_left", "breast_right", "bottle", "pump", "settings",
    ]
    buttons = {}
    for i in range(1, count + 1):
        icon = icons[(i - 1) % len(icons)]
        buttons[i] = {"icon": icon, "label": icon.upper(), "action": icon}
    return buttons


renderer = ScreenRenderer()


class TestScreenRenderer:
    def test_renders_empty_screen(self):
        from baby_macropad.ui.framework.screen import ScreenDef
        screen = ScreenDef(name="empty", cells={})
        data = renderer.render(screen)
        _validate_jpeg(data)


class TestHomeGrid:
    def test_15_buttons_produces_15_cells(self):
        buttons = _make_buttons(15)
        screen = build_home_grid(buttons)
        assert len(screen.cells) == 15

    def test_renders_valid_jpeg(self):
        buttons = _make_buttons(15)
        screen = build_home_grid(buttons)
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_with_sleep_active(self):
        buttons = _make_buttons(15)
        # Key 13 is sleep in our test config
        runtime_state = {13: "active:1h 30m"}
        screen = build_home_grid(buttons, runtime_state=runtime_state)
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_with_suggested_breast(self):
        buttons = _make_buttons(15)
        # Keys 11, 6 are breast_left/breast_right in our config
        runtime_state = {11: "suggested"}
        screen = build_home_grid(buttons, runtime_state=runtime_state)
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_on_press_format(self):
        buttons = _make_buttons(3)
        screen = build_home_grid(buttons)
        for cell in screen.cells.values():
            assert cell.on_press is not None
            assert cell.on_press.startswith("home:")


class TestDetailScreen:
    def test_renders_valid_jpeg(self):
        screen = build_detail_screen(
            title="LEFT BREAST",
            options=[
                {"label": "LEFT", "key_num": 11, "selected": True},
                {"label": "RIGHT", "key_num": 12, "selected": False},
            ],
            timer_seconds=45,
            category_color=(102, 204, 102),
        )
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_has_back_at_key_1(self):
        screen = build_detail_screen(
            title="TEST",
            options=[],
            timer_seconds=30,
            category_color=(102, 204, 102),
        )
        assert 1 in screen.cells
        assert screen.cells[1].on_press == "back"

    def test_four_options(self):
        screen = build_detail_screen(
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
        data = renderer.render(screen)
        _validate_jpeg(data)


class TestConfirmationScreen:
    def test_renders_valid_jpeg(self):
        screen = build_confirmation_screen(
            action_label="Left breast logged",
            context_line="Next: Right breast",
            icon_name="bottle",
            category_color=(102, 204, 102),
        )
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_column_fill_visible(self):
        """Column fill celebration should produce non-background pixels in the column."""
        screen = build_confirmation_screen(
            action_label="Logged",
            context_line="",
            icon_name="moon",
            category_color=(102, 153, 204),
            celebration_style="color_fill",
            column_index=2,
        )
        data = renderer.render(screen)
        img = _validate_jpeg(data)
        # Sample a pixel in column 2, row 0 area — should not be pure background
        # VIS_COL_X[2]=203, VIS_ROW_Y[0]=10
        px = img.getpixel((220, 30))
        bg = (28, 28, 30)
        assert px != bg, f"Expected non-background pixel at column 2, got {px}"

    def test_no_celebration(self):
        screen = build_confirmation_screen(
            action_label="Pee logged",
            context_line="",
            icon_name="diaper",
            category_color=(204, 170, 68),
            celebration_style="none",
        )
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_undo_at_key_1(self):
        screen = build_confirmation_screen(
            action_label="Test",
            context_line="",
            icon_name="moon",
            category_color=(102, 153, 204),
        )
        assert 1 in screen.cells
        assert screen.cells[1].on_press == "undo"


class TestSelectionScreen:
    def test_renders_valid_jpeg(self):
        items = [{"label": f"Cat {i}"} for i in range(5)]
        screen = build_selection_screen(items, accent_color=(153, 153, 153))
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_14_items_fills_all_slots(self):
        items = [{"label": f"Item {i}"} for i in range(14)]
        screen = build_selection_screen(items, accent_color=(153, 153, 153))
        # 14 items + 1 BACK = 15 cells
        assert len(screen.cells) == 15

    def test_back_at_key_1(self):
        items = [{"label": "A"}]
        screen = build_selection_screen(items, accent_color=(153, 153, 153))
        assert 1 in screen.cells
        assert screen.cells[1].on_press == "back"

    def test_select_on_press_format(self):
        items = [{"label": f"X{i}"} for i in range(3)]
        screen = build_selection_screen(items, accent_color=(153, 153, 153))
        # Item cells should have select:N on_press
        for i in range(3):
            key = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 2, 3, 4, 5][i]
            assert screen.cells[key].on_press == f"select:{i}"

    def test_with_icons(self):
        items = [
            {"label": "Feeding", "icon": "bottle"},
            {"label": "Notes", "icon": "note"},
        ]
        screen = build_selection_screen(items, accent_color=(153, 153, 153))
        data = renderer.render(screen)
        _validate_jpeg(data)


class TestSettingsScreen:
    def test_renders_valid_jpeg(self):
        settings = SettingsModel()
        screen = build_settings_screen(settings)
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_auto_generates_from_model(self):
        settings = SettingsModel()
        screen = build_settings_screen(settings)
        # Should have cards for non-hidden fields + BACK
        # Non-hidden fields: timer_duration_seconds, skip_breast_detail,
        # celebration_style, brightness = 4 fields + 1 BACK = 5 cells
        assert len(screen.cells) == 5

    def test_back_at_key_1(self):
        settings = SettingsModel()
        screen = build_settings_screen(settings)
        assert 1 in screen.cells
        assert screen.cells[1].on_press == "back"

    def test_cycle_on_press(self):
        settings = SettingsModel()
        screen = build_settings_screen(settings)
        # First setting card at key 11 should have cycle:field_name
        assert 11 in screen.cells
        assert screen.cells[11].on_press.startswith("cycle:")


class TestSleepScreen:
    def test_renders_valid_jpeg(self):
        screen = build_sleep_screen(elapsed_minutes=45, start_time_str="10:14 PM")
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_wake_up_at_key_13(self):
        screen = build_sleep_screen(elapsed_minutes=0, start_time_str="11:00 PM")
        assert 13 in screen.cells
        assert screen.cells[13].on_press == "wake_up"

    def test_all_other_keys_wake_screen(self):
        screen = build_sleep_screen(elapsed_minutes=30, start_time_str="9:00 PM")
        for key in range(1, 16):
            assert key in screen.cells
            if key != 13:
                assert screen.cells[key].on_press == "wake_screen"

    def test_hours_format(self):
        screen = build_sleep_screen(elapsed_minutes=125, start_time_str="8:30 PM")
        data = renderer.render(screen)
        _validate_jpeg(data)


class TestDashboardScreen:
    def test_renders_valid_jpeg_no_data(self):
        screen = build_dashboard_screen(dashboard_data=None, connected=False, queued_count=0)
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_renders_valid_jpeg_with_data(self):
        data = {
            "active_sleep": None,
            "last_sleep": None,
            "last_feeding": {"type": "breast", "started_side": "left", "created_at": "2026-02-27T10:00:00Z"},
            "last_diaper": {"type": "pee", "created_at": "2026-02-27T09:30:00Z"},
            "today_counts": {"feedings": 5, "pee": 3, "poop": 1, "sleep_hours": 2.5},
            "suggested_side": "right",
        }
        screen = build_dashboard_screen(dashboard_data=data, connected=True, queued_count=0)
        result = renderer.render(screen)
        _validate_jpeg(result)

    def test_empty_cells(self):
        screen = build_dashboard_screen()
        assert len(screen.cells) == 0


class TestDeterminism:
    def test_same_input_same_output(self):
        """Same ScreenDef input should produce identical JPEG bytes."""
        buttons = _make_buttons(15)
        screen1 = build_home_grid(buttons)
        screen2 = build_home_grid(buttons)
        data1 = renderer.render(screen1)
        data2 = renderer.render(screen2)
        assert data1 == data2
