"""Tests for the thread-safe StateMachine."""

import threading
import time

from baby_macropad.state import DisplayState
from baby_macropad.ui.state_machine import DEBOUNCE_SECONDS, KeySnapshot, StateMachine, TickAction


class TestTryHandleKey:
    def test_returns_snapshot(self):
        sm = StateMachine(DisplayState())
        snap = sm.try_handle_key(5)
        assert isinstance(snap, KeySnapshot)
        assert snap.mode == "home_grid"

    def test_debounce_blocks_rapid_press(self):
        sm = StateMachine(DisplayState())
        snap1 = sm.try_handle_key(5)
        assert snap1 is not None
        # Immediate second press should be debounced
        snap2 = sm.try_handle_key(5)
        assert snap2 is None

    def test_debounce_allows_after_interval(self):
        sm = StateMachine(DisplayState())
        snap1 = sm.try_handle_key(5)
        assert snap1 is not None
        time.sleep(DEBOUNCE_SECONDS + 0.01)
        snap2 = sm.try_handle_key(5)
        assert snap2 is not None

    def test_different_keys_not_debounced(self):
        sm = StateMachine(DisplayState())
        snap1 = sm.try_handle_key(5)
        snap2 = sm.try_handle_key(6)
        assert snap1 is not None
        assert snap2 is not None

    def test_snapshot_captures_current_mode(self):
        state = DisplayState()
        state.mode = "confirmation"
        sm = StateMachine(state)
        snap = sm.try_handle_key(1)
        assert snap.mode == "confirmation"

    def test_snapshot_is_copy(self):
        sm = StateMachine(DisplayState())
        snap = sm.try_handle_key(1)
        # Mutating the snapshot should not affect the real state
        snap.state.mode = "settings"
        assert sm.mode == "home_grid"


class TestAdvanceTick:
    def test_confirmation_expiry(self):
        sm = StateMachine(DisplayState())
        sm.enter_confirmation(
            "test", "label", "ctx", "icon", (255, 0, 0), 0,
            expires=time.monotonic() - 1.0,
        )
        assert sm.mode == "confirmation"
        tick = sm.advance_tick(time.monotonic())
        assert tick.action == "confirmation_expired"
        assert sm.mode == "home_grid"

    def test_confirmation_not_expired(self):
        sm = StateMachine(DisplayState())
        sm.enter_confirmation(
            "test", "label", "ctx", "icon", (255, 0, 0), 0,
            expires=time.monotonic() + 100.0,
        )
        tick = sm.advance_tick(time.monotonic())
        assert tick.action == "none"

    def test_detail_expiry(self):
        sm = StateMachine(DisplayState())
        sm.enter_detail("breast_left", [], 0, {}, time.monotonic() - 1.0)
        tick = sm.advance_tick(time.monotonic())
        assert tick.action == "detail_expired"

    def test_detail_refresh(self):
        sm = StateMachine(DisplayState())
        sm.enter_detail("breast_left", [], 0, {}, time.monotonic() + 100.0)
        tick = sm.advance_tick(time.monotonic())
        assert tick.action == "refresh"

    def test_sleep_mode_refresh(self):
        sm = StateMachine(DisplayState())
        sm.enter_sleep_mode("s1", "2026-02-27T10:00:00Z")
        tick = sm.advance_tick(time.monotonic())
        assert tick.action == "refresh"
        assert tick.mode == "sleep_mode"

    def test_home_grid_no_action(self):
        sm = StateMachine(DisplayState())
        tick = sm.advance_tick(time.monotonic())
        assert tick.action == "none"


class TestTransitions:
    def test_enter_detail(self):
        sm = StateMachine(DisplayState())
        sm.enter_detail("bottle", [{"label": "A"}], 0, {}, 999.0)
        assert sm.mode == "detail"
        assert sm.get_detail_action() == "bottle"

    def test_enter_confirmation(self):
        sm = StateMachine(DisplayState())
        sm.enter_confirmation("test", "OK", "ctx", "icon", (0, 255, 0), 2, 999.0, "rid", "feedings")
        assert sm.mode == "confirmation"
        assert sm.get_confirmation_resource_id() == "rid"
        assert sm.get_confirmation_resource_type() == "feedings"

    def test_enter_sleep_mode(self):
        sm = StateMachine(DisplayState())
        sm.enter_sleep_mode("s1", "2026-02-27T10:00:00Z")
        assert sm.mode == "sleep_mode"
        assert sm.get_sleep_id() == "s1"

    def test_exit_sleep_mode(self):
        sm = StateMachine(DisplayState())
        sm.enter_sleep_mode("s1", "2026-02-27T10:00:00Z")
        sm.exit_sleep_mode()
        assert sm.state.sleep_active is False

    def test_return_home(self):
        sm = StateMachine(DisplayState())
        sm.enter_detail("test", [], 0, {}, 999.0)
        sm.return_home()
        assert sm.mode == "home_grid"

    def test_push_and_remove_recent_action(self):
        sm = StateMachine(DisplayState())
        sm.push_recent_action({"resource_id": "r1"})
        assert len(sm.state.recent_actions) == 1
        sm.remove_recent_action("r1")
        assert len(sm.state.recent_actions) == 0


class TestConcurrentThreadSafety:
    def test_atomic_snapshot_consistency(self):
        """Concurrent key handler and tick thread should never see inconsistent state.

        Uses a threading.Barrier to synchronize both threads so they
        attempt to read/write state at the same instant.
        """
        sm = StateMachine(DisplayState())
        sm.enter_confirmation(
            "test", "label", "ctx", "icon", (255, 0, 0), 0,
            expires=time.monotonic() + 0.1,
        )

        results = {"snap_modes": [], "tick_actions": []}
        barrier = threading.Barrier(2, timeout=5)
        errors = []

        def key_thread():
            try:
                for _ in range(100):
                    barrier.wait()
                    snap = sm.try_handle_key(1)
                    if snap:
                        results["snap_modes"].append(snap.mode)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def tick_thread():
            try:
                for _ in range(100):
                    barrier.wait()
                    tick = sm.advance_tick(time.monotonic())
                    results["tick_actions"].append(tick.action)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=key_thread)
        t2 = threading.Thread(target=tick_thread)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # No exceptions should have occurred
        assert not errors, f"Thread errors: {errors}"

    def test_no_attribute_error_under_load(self):
        """100 key presses from one thread + advance_tick at 100Hz should not crash."""
        sm = StateMachine(DisplayState())
        errors = []

        def key_thread():
            try:
                for i in range(100):
                    sm.try_handle_key((i % 15) + 1)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def tick_thread():
            try:
                for _ in range(100):
                    sm.advance_tick(time.monotonic())
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=key_thread)
        t2 = threading.Thread(target=tick_thread)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"Errors under load: {errors}"

    def test_rapid_double_press_at_180ms(self):
        """Two presses 180ms apart (> 150ms debounce) should both register."""
        sm = StateMachine(DisplayState())
        snap1 = sm.try_handle_key(5)
        assert snap1 is not None
        time.sleep(0.18)
        snap2 = sm.try_handle_key(5)
        assert snap2 is not None
