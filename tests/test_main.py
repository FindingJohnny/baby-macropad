"""Tests for the MacropadController using stub device and mocked API."""

import textwrap
from datetime import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from baby_macropad.actions.baby_basics import DashboardData
from baby_macropad.config import load_config
from baby_macropad.device import StubDevice
from baby_macropad.main import MacropadController, _in_time_range

API_URL = "https://example.com/api/v1"
CHILD_ID = "child-uuid-123"
BASE = f"{API_URL}/children/{CHILD_ID}"


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(textwrap.dedent("""\
        baby_basics:
          api_url: "https://example.com/api/v1"
          token: "bb_test_token"
          child_id: "child-uuid-123"

        buttons:
          12:
            label: "PEE"
            icon: "diaper_pee"
            action: "baby_basics.log_diaper"
            params:
              type: "pee"
            feedback:
              success_led: [204, 170, 68]
          13:
            label: "SLEEP"
            icon: "sleep"
            action: "baby_basics.toggle_sleep"
            params: {}
            feedback:
              success_led: [102, 153, 204]
          10:
            label: "Note"
            icon: "note"
            action: "baby_basics.log_note"
            params:
              content: "Quick note logged"
    """))
    return config


@pytest.fixture
def config(config_file: Path):
    return load_config(config_file)


@pytest.fixture
def controller(config, tmp_path: Path):
    ctrl = MacropadController(config)
    # Replace with stub device
    ctrl._device = StubDevice()
    ctrl._device.open()
    # Use isolated queue per test
    ctrl.queue.close()
    from baby_macropad.offline.queue import OfflineQueue
    ctrl.queue = OfflineQueue(db_path=tmp_path / "test_queue.db")
    ctrl.sync_worker.queue = ctrl.queue
    return ctrl


@respx.mock
def test_dispatch_feeding(controller: MacropadController):
    respx.post(f"{BASE}/feedings").mock(
        return_value=Response(201, json={"feeding": {"id": "f1"}})
    )
    result = controller._dispatch_action(
        "baby_basics.log_feeding",
        {"type": "breast", "started_side": "left"},
    )
    assert result["feeding"]["id"] == "f1"


@respx.mock
def test_dispatch_diaper(controller: MacropadController):
    respx.post(f"{BASE}/diapers").mock(
        return_value=Response(201, json={"diaper": {"id": "d1"}})
    )
    result = controller._dispatch_action("baby_basics.log_diaper", {"type": "pee"})
    assert result["diaper"]["id"] == "d1"


@respx.mock
def test_dispatch_sleep_toggle(controller: MacropadController):
    respx.post(f"{BASE}/sleeps").mock(
        return_value=Response(201, json={"sleep": {"id": "s1"}})
    )
    result = controller._dispatch_action("baby_basics.toggle_sleep", {})
    assert result["sleep"]["id"] == "s1"


@respx.mock
def test_dispatch_note(controller: MacropadController):
    respx.post(f"{BASE}/notes").mock(
        return_value=Response(201, json={"note": {"id": "n1"}})
    )
    result = controller._dispatch_action(
        "baby_basics.log_note",
        {"content": "Quick note logged"},
    )
    assert result["note"]["id"] == "n1"


def test_dispatch_unknown_action_raises(controller: MacropadController):
    with pytest.raises(ValueError, match="Unknown action"):
        controller._dispatch_action("unknown.action", {})


def test_dispatch_ha_action_is_noop(controller: MacropadController):
    result = controller._dispatch_action("home_assistant.toggle", {"entity_id": "light.test"})
    assert result is None


def test_key_press_enters_detail(controller: MacropadController):
    """Pressing PEE button enters detail screen for pre-confirmation."""
    # Physical key 2 → remapped to logical key 12 (PEE)
    controller._on_key_press(2, True)
    assert controller._sm.mode == "detail"


@respx.mock
def test_key_press_success(controller: MacropadController):
    respx.post(f"{BASE}/diapers").mock(
        return_value=Response(201, json={"diaper": {"id": "d1"}})
    )
    respx.get(f"{BASE}/dashboard").mock(
        return_value=Response(200, json={"dashboard": {}})
    )

    # Physical key 2 → logical 12 (PEE) → enters detail
    controller._on_key_press(2, True)
    assert controller._sm.mode == "detail"

    # Simulate timer expiry → commits default option → API called
    controller._commit_detail_default()

    # Verify the API was called
    assert respx.routes[0].called


@respx.mock
def test_key_press_offline_queues_event(controller: MacropadController):
    respx.post(f"{BASE}/diapers").mock(side_effect=ConnectionError("No network"))
    respx.get(f"{BASE}/dashboard").mock(side_effect=ConnectionError("No network"))

    # Physical key 2 → logical 12 (PEE) → enters detail
    controller._on_key_press(2, True)
    assert controller._sm.mode == "detail"

    # Simulate timer expiry → commits default option → queued offline
    controller._commit_detail_default()

    # Wait briefly for background refresh thread to finish
    import time
    time.sleep(0.1)

    assert controller.queue.count() >= 1
    events = controller.queue.peek()
    assert events[0].action == "baby_basics.log_diaper"
    assert events[0].params == {"type": "pee"}


def test_key_release_ignored(controller: MacropadController):
    """Key release events should not trigger actions."""
    controller._dispatch_action = MagicMock()
    controller._on_key_press(2, False)  # Release (physical key 2 → logical 12)
    controller._dispatch_action.assert_not_called()


def test_unconfigured_key_ignored(controller: MacropadController):
    """Pressing a key not in the config should be a no-op."""
    controller._dispatch_action = MagicMock()
    # Physical key 9 → remapped to logical key 9 (middle row, not in config)
    controller._on_key_press(9, True)
    controller._dispatch_action.assert_not_called()


def test_remap_key_swaps_top_bottom_rows():
    """Physical top row (1-5) maps to logical top (11-15) and vice versa."""
    remap = MacropadController._remap_key
    # Top row physical → logical
    assert remap(1) == 11
    assert remap(2) == 12
    assert remap(5) == 15
    # Middle row unchanged
    assert remap(6) == 6
    assert remap(10) == 10
    # Bottom row physical → logical
    assert remap(11) == 1
    assert remap(15) == 5


def test_controller_stop(controller: MacropadController):
    """Stop should clean up without errors."""
    controller.stop()
    assert controller._shutdown.is_set()


# --- _in_time_range tests ---

def test_in_time_range_non_wrapping():
    """Time inside a non-wrapping range returns True."""
    assert _in_time_range(time(12, 0), time(10, 0), time(18, 0)) is True


def test_in_time_range_non_wrapping_outside():
    """Time before a non-wrapping range returns False."""
    assert _in_time_range(time(8, 0), time(10, 0), time(18, 0)) is False


def test_in_time_range_midnight_crossing():
    """Time after start in an overnight range (start > end) returns True."""
    assert _in_time_range(time(22, 0), time(20, 0), time(6, 0)) is True


def test_in_time_range_midnight_crossing_inside_morning():
    """Time before end in an overnight range (start > end) returns True."""
    assert _in_time_range(time(3, 0), time(20, 0), time(6, 0)) is True


def test_in_time_range_midnight_crossing_outside():
    """Time between end and start in an overnight range returns False."""
    assert _in_time_range(time(12, 0), time(20, 0), time(6, 0)) is False


def test_in_time_range_boundary():
    """Start is inclusive; end is exclusive."""
    assert _in_time_range(time(10, 0), time(10, 0), time(18, 0)) is True
    assert _in_time_range(time(18, 0), time(10, 0), time(18, 0)) is False


# --- Sleep flow tests ---

@respx.mock
def test_sleep_toggle_starts_sleep(controller: MacropadController):
    """_handle_sleep_toggle() with no active sleep starts one and enters sleep_mode."""
    respx.post(f"{BASE}/sleeps").mock(
        return_value=Response(
            201, json={"sleep": {"id": "s1", "start_time": "2026-01-01T00:00:00Z"}}
        )
    )
    respx.get(f"{BASE}/dashboard").mock(
        return_value=Response(200, json={"dashboard": {}})
    )
    controller._handle_sleep_toggle()
    assert controller._sm.mode == "sleep_mode"


def test_controller_has_display_lock(controller: MacropadController):
    """Controller should have a _display_lock attribute."""
    assert hasattr(controller, "_display_lock")
    import threading
    assert isinstance(controller._display_lock, type(threading.Lock()))


def test_celebration_none_skips_rendering(controller: MacropadController):
    """_play_celebration with style='none' should not render any frames."""
    device = controller._device
    device.set_screen_image = MagicMock()
    controller._dispatcher._play_celebration(
        category_color=(102, 204, 102),
        icon="breast_left",
        label="Fed L",
        context="",
        style="none",
    )
    device.set_screen_image.assert_not_called()


def test_settings_synced_on_startup(controller: MacropadController):
    """After construction, state machine should have SettingsModel defaults."""
    state = controller._sm.state
    assert state.timer_seconds == 7
    assert state.celebration_style == "color_fill"
    assert state.skip_breast_detail is False


def test_dashboard_refresh_marks_home_dirty(controller: MacropadController):
    """After _refresh_dashboard, home_dirty should be True."""
    import respx as rx
    with rx.mock:
        rx.get(f"{BASE}/dashboard").mock(
            return_value=Response(200, json={"dashboard": {}})
        )
        controller._refresh_dashboard()
    assert controller._sm.state._home_dirty is True


def test_tick_clears_dirty_on_home_refresh(controller: MacropadController):
    """Tick loop handler clears dirty flag when refreshing home grid."""
    controller._sm.mark_home_dirty()
    # Simulate what _display_tick_loop does for home_grid refresh
    import time as t
    tick = controller._sm.advance_tick(t.monotonic())
    assert tick.action == "refresh"
    assert tick.mode == "home_grid"
    assert controller._sm.clear_home_dirty() is True
    assert controller._sm.clear_home_dirty() is False


def test_sleep_toggle_active_enters_wake_confirm(controller: MacropadController):
    """_handle_sleep_toggle() with active_sleep in dashboard enters wake_confirm."""
    active_sleep = {"id": "s1", "start_time": "2026-01-01T00:00:00Z"}
    dashboard = DashboardData(active_sleep=active_sleep)
    controller._sm.set_dashboard(dashboard, True, 0)
    controller._handle_sleep_toggle()
    assert controller._sm.mode == "wake_confirm"


@respx.mock
def test_optimistic_update_after_feeding(controller: MacropadController):
    """After logging a breast feeding, suggested_side flips and count increments."""
    dashboard = DashboardData(
        suggested_side="left",
        today_counts={"feedings": 2, "diapers": 1},
    )
    controller._sm.set_dashboard(dashboard, True, 0)
    respx.post(f"{BASE}/feedings").mock(
        return_value=Response(201, json={"feeding": {"id": "f1"}})
    )
    respx.get(f"{BASE}/dashboard").mock(
        return_value=Response(200, json={"dashboard": {}})
    )
    controller._dispatcher.call_api_and_confirm(
        "baby_basics.log_feeding",
        {"type": "breast", "started_side": "left"},
        "Fed L", "breast_left", (102, 204, 102), "feeding", 0, "feedings",
    )
    assert dashboard.suggested_side == "right"
    assert dashboard.today_counts["feedings"] == 3


@respx.mock
def test_optimistic_update_after_diaper(controller: MacropadController):
    """After logging a diaper, count increments."""
    dashboard = DashboardData(
        today_counts={"feedings": 2, "diapers": 4},
    )
    controller._sm.set_dashboard(dashboard, True, 0)
    respx.post(f"{BASE}/diapers").mock(
        return_value=Response(201, json={"diaper": {"id": "d1"}})
    )
    respx.get(f"{BASE}/dashboard").mock(
        return_value=Response(200, json={"dashboard": {}})
    )
    controller._dispatcher.call_api_and_confirm(
        "baby_basics.log_diaper",
        {"type": "pee"},
        "Pee", "diaper_pee", (204, 170, 68), "diaper", 1, "diapers",
    )
    assert dashboard.today_counts["diapers"] == 5
