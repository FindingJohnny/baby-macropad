"""Tests for the MacropadController using stub device and mocked API."""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import respx
from httpx import Response

from baby_macropad.config import load_config
from baby_macropad.device import StubDevice
from baby_macropad.main import MacropadController

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
