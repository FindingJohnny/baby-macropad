"""Sleep lifecycle management: start, wake confirm, end."""
from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable

import httpx

from baby_macropad.actions.baby_basics import BabyBasicsAPIError

if TYPE_CHECKING:
    from baby_macropad.actions.baby_basics import BabyBasicsClient
    from baby_macropad.device import DeviceProtocol
    from baby_macropad.ui.led import LedController
    from baby_macropad.ui.state_machine import StateMachine

logger = logging.getLogger(__name__)

CONFIRMATION_DURATION = 5.0


class SleepManager:
    def __init__(
        self,
        get_api: Callable[[], BabyBasicsClient],
        sm: StateMachine,
        led: LedController,
        device: DeviceProtocol,
        get_queue: Any,  # callable returning OfflineQueue
        brightness: int,
        refresh_display: Any,  # callback
        refresh_dashboard: Any,  # callback
    ) -> None:
        self._get_api = get_api
        self._sm = sm
        self._led = led
        self._device = device
        self._get_queue = get_queue
        self._brightness = brightness
        self._refresh_display = refresh_display
        self._refresh_dashboard = refresh_dashboard

    def handle_sleep_toggle(self) -> None:
        from baby_macropad.actions.baby_basics import DashboardData
        dashboard = self._sm.state.dashboard
        active = isinstance(dashboard, DashboardData) and dashboard.active_sleep
        if active:
            sleep_id = dashboard.active_sleep.get("id")
            if sleep_id:
                if not self._sm.state.sleep_active:
                    self._sm.sync_sleep_active(
                        True, sleep_id, dashboard.active_sleep.get("start_time")
                    )
                self.enter_wake_confirm()
            return
        try:
            result = self._get_api().start_sleep()
            data = result.get("sleep", result)
            start_time = data.get("start_time", datetime.now(UTC).isoformat())
            self._sm.enter_sleep_mode(data.get("id", ""), start_time)
            self._led.flash_sleep_start()
        except (
            BabyBasicsAPIError, ConnectionError, httpx.TimeoutException, httpx.ConnectError
        ) as e:
            logger.warning("Failed to start sleep: %s", e)
            self._get_queue().enqueue("baby_basics.toggle_sleep", {})
            self._sm.enter_sleep_mode("pending", datetime.now(UTC).isoformat())
            self._led.flash_queued()
        self._device.set_brightness(10)
        self._refresh_display()

    def enter_wake_confirm(self, from_sleep: bool = False) -> None:
        """Show wake confirmation screen before ending sleep."""
        if from_sleep:
            expires = 0.0  # No timeout — sleep data page stays indefinitely
        else:
            timer = self._sm.state.timer_seconds
            expires = time.monotonic() + (timer if timer > 0 else 7)
        self._sm.enter_wake_confirm(expires, from_sleep)
        self._refresh_display()

    def handle_wake_up(self) -> None:
        sleep_id = self._sm.get_sleep_id()
        if not sleep_id:
            self._sm.return_home()
            self._refresh_display()
            return
        self._end_sleep(sleep_id)

    def _end_sleep(self, sleep_id: str) -> None:
        self._device.set_brightness(self._brightness)
        try:
            self._get_api().end_sleep(sleep_id)
            start_time = self._sm.get_sleep_start_time()
            duration_str = self._calc_duration_str(start_time)
            self._sm.exit_sleep_mode(ended_id=sleep_id)
            self._led.flash_wake()
            self._sm.enter_confirmation(
                "baby_basics.end_sleep", "Awake!", duration_str,
                "sunrise", (255, 220, 150), 2,
                time.monotonic() + CONFIRMATION_DURATION, None, "sleeps",
            )
        except BabyBasicsAPIError as e:
            if e.status_code == 400:
                # Sleep already ended or invalid — clear stale state and move on
                logger.warning("Stale sleep %s (400), clearing local state", sleep_id[:8])
                self._sm.exit_sleep_mode(ended_id=sleep_id)
                self._clear_stale_active_sleep()
                self._sm.return_home()
            else:
                logger.warning("Failed to end sleep: %s", e)
                self._sm.exit_sleep_mode()
                self._sm.return_home()
                self._led.flash_error()
        except (ConnectionError, httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning("Failed to end sleep: %s", e)
            self._sm.exit_sleep_mode()
            self._sm.return_home()
            self._led.flash_error()
        self._refresh_display()
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _clear_stale_active_sleep(self) -> None:
        """Clear active_sleep from local dashboard when the API says it's invalid."""
        from baby_macropad.actions.baby_basics import DashboardData
        dashboard = self._sm.state.dashboard
        if isinstance(dashboard, DashboardData):
            dashboard.active_sleep = None
        self._sm.state.sleep_active = False
        self._sm.state.sleep_id = None

    def _calc_duration_str(self, start_time: str | None) -> str:
        if not start_time:
            return "Sleep ended"
        try:
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            secs = (datetime.now(UTC) - start).total_seconds()
            h, m = int(secs // 3600), int((secs % 3600) // 60)
            return f"Slept {h}h {m}m" if h > 0 else f"Slept {m}m"
        except (ValueError, TypeError):
            return "Sleep ended"
