"""Thread-safe state machine for the macropad controller.

Wraps DisplayState with an RLock to prevent race conditions between
the key handler thread and the tick thread. All state reads and writes
go through StateMachine methods.
"""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from typing import Any

from baby_macropad.state import DisplayState, ScreenMode

# Debounce reduced from 300ms to 150ms (allows genuine rapid presses)
DEBOUNCE_SECONDS = 0.15


@dataclass
class KeySnapshot:
    """Atomic snapshot of state at key press time."""

    mode: ScreenMode
    state: DisplayState


@dataclass
class TickAction:
    """What the tick loop should do after advance_tick."""

    action: str  # "none", "confirmation_expired", "detail_expired", "refresh"
    mode: ScreenMode = "home_grid"


class StateMachine:
    """Thread-safe wrapper around DisplayState.

    The RLock allows reentrant acquisition so a method that holds the lock
    can call another method that also acquires it.
    """

    def __init__(self, initial_state: DisplayState) -> None:
        self._state = initial_state
        self._lock = threading.RLock()
        self._last_key_press: dict[int, float] = {}

    @property
    def mode(self) -> ScreenMode:
        with self._lock:
            return self._state.mode

    @property
    def state(self) -> DisplayState:
        """Direct access for reads that don't need snapshot semantics."""
        return self._state

    def try_handle_key(self, key_num: int) -> KeySnapshot | None:
        """Acquire lock, check debounce, return atomic snapshot.

        Returns None if the key should be ignored (debounce).
        """
        now = time.monotonic()
        with self._lock:
            last = self._last_key_press.get(key_num, 0.0)
            if now - last < DEBOUNCE_SECONDS:
                return None
            self._last_key_press[key_num] = now
            return KeySnapshot(
                mode=self._state.mode,
                state=copy.copy(self._state),
            )

    def advance_tick(self, now: float) -> TickAction:
        """Called by tick thread. Checks timers, fires auto-transitions.

        Returns what action the controller should take.
        """
        with self._lock:
            s = self._state

            # Confirmation auto-dismiss
            if s.mode == "confirmation" and now >= s.confirmation_expires:
                s.return_home()
                return TickAction(action="confirmation_expired", mode="home_grid")

            # Detail screen: auto-commit on timer expiry
            if s.mode == "detail":
                if s.detail_timer_expires > 0 and now >= s.detail_timer_expires:
                    return TickAction(action="detail_expired", mode="detail")
                # Refresh countdown display
                return TickAction(action="refresh", mode="detail")

            # Sleep mode: refresh elapsed timer
            if s.mode == "sleep_mode":
                return TickAction(action="refresh", mode="sleep_mode")

            return TickAction(action="none", mode=s.mode)

    # --- Transition methods ---

    def enter_detail(
        self,
        action: str,
        options: list[dict],
        default_index: int,
        context: dict,
        timer_expires: float,
    ) -> None:
        with self._lock:
            self._state.enter_detail(action, options, default_index, context, timer_expires)

    def enter_confirmation(
        self,
        action: str,
        label: str,
        context: str,
        icon: str,
        category_color: tuple[int, int, int],
        column: int,
        expires: float,
        resource_id: str | None = None,
        resource_type: str | None = None,
    ) -> None:
        with self._lock:
            self._state.enter_confirmation(
                action, label, context, icon, category_color,
                column, expires, resource_id, resource_type,
            )

    def enter_sleep_mode(self, sleep_id: str, start_time: str) -> None:
        with self._lock:
            self._state.enter_sleep_mode(sleep_id, start_time)

    def exit_sleep_mode(self) -> None:
        with self._lock:
            self._state.exit_sleep_mode()

    def return_home(self) -> None:
        with self._lock:
            self._state.return_home()

    def push_recent_action(self, action: dict) -> None:
        with self._lock:
            self._state.push_recent_action(action)

    # --- State accessors (locked reads) ---

    def get_detail_action(self) -> str | None:
        with self._lock:
            return self._state.detail_action

    def get_sleep_id(self) -> str | None:
        with self._lock:
            return self._state.sleep_id

    def get_sleep_start_time(self) -> str | None:
        with self._lock:
            return self._state.sleep_start_time

    def get_confirmation_resource_id(self) -> str | None:
        with self._lock:
            return self._state.confirmation_resource_id

    def get_confirmation_resource_type(self) -> str | None:
        with self._lock:
            return self._state.confirmation_resource_type

    # --- State mutators (locked writes) ---

    def set_dashboard(self, dashboard: Any, connected: bool, queued_count: int) -> None:
        with self._lock:
            self._state.dashboard = dashboard
            self._state.connected = connected
            self._state.queued_count = queued_count

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self._state.connected = connected

    def set_queued_count(self, count: int) -> None:
        with self._lock:
            self._state.queued_count = count

    def set_sleep_from_dashboard(self, sleep_id: str | None, start_time: str | None) -> None:
        """Update sleep state from dashboard poll (if not already in sleep mode)."""
        with self._lock:
            if self._state.mode != "sleep_mode":
                self._state.sleep_active = sleep_id is not None
                self._state.sleep_id = sleep_id
                self._state.sleep_start_time = start_time

    def remove_recent_action(self, resource_id: str) -> None:
        with self._lock:
            self._state.recent_actions = [
                a for a in self._state.recent_actions
                if a.get("resource_id") != resource_id
            ]
