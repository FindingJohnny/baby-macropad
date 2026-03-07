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
from baby_macropad.ui.screens.data_page import build_data_page, DataColumn, PageAction
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
                {"label": "LEFT", "key_num": 7, "selected": True},
                {"label": "RIGHT", "key_num": 8, "selected": False},
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

    def test_timer_at_key_15(self):
        screen = build_detail_screen(
            title="TEST",
            options=[],
            timer_seconds=30,
            category_color=(102, 204, 102),
        )
        assert 15 in screen.cells

    def test_header_row_colored(self):
        screen = build_detail_screen(
            title="TEST",
            options=[],
            timer_seconds=30,
            category_color=(102, 204, 102),
        )
        for key in (11, 12, 13, 14, 15):
            assert key in screen.cells

    def test_four_options(self):
        screen = build_detail_screen(
            title="DIAPER",
            options=[
                {"label": "PEE", "key_num": 6, "selected": False},
                {"label": "POOP", "key_num": 7, "selected": True},
                {"label": "BOTH", "key_num": 8, "selected": False},
                {"label": "DRY", "key_num": 9, "selected": False},
            ],
            timer_seconds=10,
            category_color=(204, 170, 68),
        )
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_radio_indicators_in_labels(self):
        screen = build_detail_screen(
            title="TEST",
            options=[
                {"label": "LEFT", "key_num": 7, "selected": True},
                {"label": "RIGHT", "key_num": 8, "selected": False},
            ],
            timer_seconds=5,
            category_color=(102, 204, 102),
        )
        # Selected option should have filled radio ●
        selected_widget = screen.cells[7].widget
        assert "\u25cf" in selected_widget.child.text
        # Unselected option should have empty radio ○
        unselected_widget = screen.cells[8].widget
        assert "\u25cb" in unselected_widget.child.text

    def test_log_button_shown_when_enabled(self):
        screen = build_detail_screen(
            title="TEST",
            options=[{"label": "A", "key_num": 7, "selected": True}],
            timer_seconds=5,
            category_color=(102, 204, 102),
            show_log_button=True,
        )
        assert 5 in screen.cells
        assert screen.cells[5].on_press == "commit_log"
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_log_button_hidden_by_default(self):
        screen = build_detail_screen(
            title="TEST",
            options=[{"label": "A", "key_num": 7, "selected": True}],
            timer_seconds=5,
            category_color=(102, 204, 102),
        )
        assert 5 not in screen.cells


class TestConfirmationScreen:
    """Test all 5 confirmation layout variants."""

    _LAYOUTS = ["banner", "center_stage", "full_icon", "split", "minimal", "data"]
    _COLOR = (102, 204, 102)

    def test_all_layouts_render_valid_jpeg(self):
        for layout in self._LAYOUTS:
            screen = build_confirmation_screen(
                action_label="Fed L",
                context_line="5 feedings",
                category_color=self._COLOR,
                icon="breast_left",
                layout=layout,
            )
            data = renderer.render(screen)
            _validate_jpeg(data)

    def test_all_layouts_have_done_button(self):
        for layout in self._LAYOUTS:
            screen = build_confirmation_screen(
                action_label="Test",
                context_line="",
                category_color=self._COLOR,
                layout=layout,
            )
            done_found = any(
                c.on_press == "done" for c in screen.cells.values()
            )
            assert done_found, f"Layout '{layout}' missing DONE button"

    def test_all_layouts_show_undo_with_resource_id(self):
        for layout in self._LAYOUTS:
            screen = build_confirmation_screen(
                action_label="Test",
                context_line="",
                category_color=self._COLOR,
                resource_id="abc-123",
                layout=layout,
            )
            undo_found = any(
                c.on_press == "undo" for c in screen.cells.values()
            )
            assert undo_found, f"Layout '{layout}' missing UNDO with resource_id"

    def test_all_layouts_hide_undo_without_resource_id(self):
        for layout in self._LAYOUTS:
            screen = build_confirmation_screen(
                action_label="Test",
                context_line="",
                category_color=self._COLOR,
                layout=layout,
            )
            undo_found = any(
                c.on_press == "undo" for c in screen.cells.values()
            )
            assert not undo_found, f"Layout '{layout}' shows UNDO without resource_id"

    def test_banner_top_row_colored(self):
        screen = build_confirmation_screen(
            action_label="Test", context_line="",
            category_color=self._COLOR, layout="banner",
        )
        for key in (11, 12, 13, 14, 15):
            assert key in screen.cells

    def test_full_icon_has_colored_background(self):
        screen = build_confirmation_screen(
            action_label="Test", context_line="",
            category_color=self._COLOR, layout="full_icon",
        )
        assert screen.background_color == self._COLOR

    def test_multiline_label(self):
        for layout in self._LAYOUTS:
            screen = build_confirmation_screen(
                action_label="Pee +\nPoop",
                context_line="3 diapers",
                category_color=(204, 170, 68),
                icon="diaper_both",
                layout=layout,
            )
            data = renderer.render(screen)
            _validate_jpeg(data)

    def test_unknown_layout_falls_back_to_banner(self):
        screen = build_confirmation_screen(
            action_label="Test", context_line="",
            category_color=self._COLOR, layout="nonexistent",
        )
        # Should not crash, falls back to banner
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_data_page_with_dashboard(self):
        from baby_macropad.actions.baby_basics import DashboardData
        dashboard = DashboardData(
            today_counts={"feedings": 5, "diapers": 3},
            suggested_side="right",
        )
        screen = build_confirmation_screen(
            action_label="Fed Left",
            context_line="Logging…",
            category_color=self._COLOR,
            icon="breast_left",
            resource_id="abc-123",
            layout="data",
            dashboard=dashboard,
        )
        data = renderer.render(screen)
        _validate_jpeg(data)
        # Should have TODAY, NEXT, and STATUS columns (3 columns → keys 7,8,9 labels + 2,3,4 values)
        assert 7 in screen.cells  # TODAY label
        assert 8 in screen.cells  # NEXT label
        assert 9 in screen.cells  # STATUS label
        assert 2 in screen.cells  # TODAY value
        assert 3 in screen.cells  # NEXT value
        assert 4 in screen.cells  # STATUS value
        # UNDO + DONE + HOME buttons
        assert screen.cells[1].on_press == "undo"
        assert screen.cells[5].on_press == "done"
        assert screen.cells[15].on_press == "done"

    def test_data_page_without_dashboard(self):
        screen = build_confirmation_screen(
            action_label="Pee",
            context_line="Logging…",
            category_color=(204, 170, 68),
            icon="diaper_pee",
            layout="data",
        )
        data = renderer.render(screen)
        _validate_jpeg(data)
        # Only STATUS column (1 column → key 7 label + key 2 value)
        assert 7 in screen.cells  # STATUS label
        assert 8 not in screen.cells  # no second column
        assert 2 in screen.cells  # STATUS value

    def test_data_page_diaper_no_next_column(self):
        from baby_macropad.actions.baby_basics import DashboardData
        dashboard = DashboardData(
            today_counts={"feedings": 5, "diapers": 3},
            suggested_side="right",
        )
        screen = build_confirmation_screen(
            action_label="Pee",
            context_line="3 diapers",
            category_color=(204, 170, 68),
            icon="diaper_pee",
            layout="data",
            dashboard=dashboard,
        )
        data = renderer.render(screen)
        _validate_jpeg(data)
        # Diaper: TODAY + STATUS (no NEXT — that's feeding-only)
        assert 7 in screen.cells  # TODAY label
        assert 8 in screen.cells  # STATUS label
        assert 9 not in screen.cells  # no 3rd column


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
        # Header row (5 cells) + 8 non-hidden settings + 1 BACK = 14 cells
        assert len(screen.cells) == 14

    def test_back_at_key_1(self):
        settings = SettingsModel()
        screen = build_settings_screen(settings)
        assert 1 in screen.cells
        assert screen.cells[1].on_press == "back"

    def test_cycle_on_press(self):
        settings = SettingsModel()
        screen = build_settings_screen(settings)
        # First setting card at key 6 (row 1, header takes row 0)
        assert 6 in screen.cells
        assert screen.cells[6].on_press.startswith("cycle:")


class TestSleepScreen:
    def test_renders_valid_jpeg(self):
        screen = build_sleep_screen(elapsed_minutes=45, start_time_str="10:14 PM")
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_wake_up_at_key_5(self):
        screen = build_sleep_screen(elapsed_minutes=0, start_time_str="11:00 PM")
        assert 5 in screen.cells
        assert screen.cells[5].on_press == "wake_up"

    def test_key_assignments(self):
        screen = build_sleep_screen(elapsed_minutes=30, start_time_str="9:00 PM")
        assert screen.cells[1].on_press == "cancel_sleep"
        assert screen.cells[5].on_press == "wake_up"
        assert screen.cells[15].on_press == "go_home"

    def test_with_feed_count(self):
        screen = build_sleep_screen(elapsed_minutes=60, start_time_str="8:00 PM", feed_count=3)
        data = renderer.render(screen)
        _validate_jpeg(data)
        # 3rd column should be present at keys 9 (label) and 4 (value)
        assert 9 in screen.cells
        assert 4 in screen.cells

    def test_header_colored(self):
        screen = build_sleep_screen(elapsed_minutes=10, start_time_str="7:00 PM")
        for key in (11, 12, 13, 14):
            assert key in screen.cells

    def test_hours_format(self):
        screen = build_sleep_screen(elapsed_minutes=125, start_time_str="8:30 PM")
        data = renderer.render(screen)
        _validate_jpeg(data)


class TestDataPage:
    def test_renders_valid_jpeg(self):
        screen = build_data_page(
            title="TEST", icon="moon", category_color=(102, 153, 204),
            columns=[
                DataColumn(label="COL1", value="Val1"),
                DataColumn(label="COL2", value="Val2"),
                DataColumn(label="COL3", value="Val3"),
            ],
            action_left=PageAction(label="BACK", on_press="back"),
            action_right=PageAction(label="GO", on_press="go"),
            action_menu=PageAction(label="HOME", on_press="home"),
        )
        data = renderer.render(screen)
        _validate_jpeg(data)

    def test_two_columns(self):
        screen = build_data_page(
            title="TWO", icon="moon", category_color=(102, 153, 204),
            columns=[
                DataColumn(label="A", value="1"),
                DataColumn(label="B", value="2"),
            ],
        )
        # Only cols 1-2 should have label/value cells
        assert 7 in screen.cells  # label col 1
        assert 8 in screen.cells  # label col 2
        assert 9 not in screen.cells  # no label col 3
        assert 2 in screen.cells  # value col 1
        assert 3 in screen.cells  # value col 2
        assert 4 not in screen.cells  # no value col 3

    def test_action_buttons(self):
        screen = build_data_page(
            title="ACT", icon="moon", category_color=(100, 100, 100),
            columns=[DataColumn(label="X", value="Y")],
            action_left=PageAction(label="LEFT", on_press="left_action"),
            action_right=PageAction(label="RIGHT", on_press="right_action"),
            action_menu=PageAction(label="MENU", on_press="menu_action"),
        )
        assert screen.cells[1].on_press == "left_action"
        assert screen.cells[5].on_press == "right_action"
        assert screen.cells[15].on_press == "menu_action"

    def test_no_actions(self):
        screen = build_data_page(
            title="NONE", icon="moon", category_color=(100, 100, 100),
            columns=[DataColumn(label="X", value="Y")],
        )
        assert 1 not in screen.cells
        assert 5 not in screen.cells
        assert 15 not in screen.cells


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
