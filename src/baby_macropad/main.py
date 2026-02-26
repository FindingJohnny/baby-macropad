"""Main entry point for the Baby Basics macropad controller."""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

from baby_macropad.actions.baby_basics import BabyBasicsAPIError, BabyBasicsClient, DashboardData
from baby_macropad.config import MacropadConfig, load_config
from baby_macropad.device import StreamDockDevice, StubDevice
from baby_macropad.offline.queue import OfflineQueue
from baby_macropad.offline.sync import SyncWorker
from baby_macropad.ui.dashboard import save_dashboard
from baby_macropad.ui.icons import generate_all_icons

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".baby-macropad" / "cache"


class MacropadController:
    """Orchestrates device, API client, offline queue, and UI rendering."""

    def __init__(self, config: MacropadConfig) -> None:
        self.config = config
        self._shutdown = threading.Event()

        # API client
        self.api_client = BabyBasicsClient(
            api_url=config.baby_basics.api_url,
            token=config.baby_basics.token,
            child_id=config.baby_basics.child_id,
        )

        # Offline queue
        self.queue = OfflineQueue()
        self.sync_worker = SyncWorker(
            queue=self.queue,
            api_client=self.api_client,
            on_sync_success=self._on_sync_success,
            on_sync_failure=self._on_sync_failure,
        )

        # Dashboard state
        self._dashboard: DashboardData | None = None
        self._connected = False

        # Device (try real, fall back to stub)
        self._device = StreamDockDevice()

    def start(self) -> None:
        """Initialize device, render UI, start listening."""
        logger.info("Starting macropad controller")

        # Try to open the real device, fall back to stub
        if not self._device.open():
            logger.info("Using stub device (no hardware found)")
            self._device = StubDevice()
            self._device.open()

        # Set brightness
        self._device.set_brightness(self.config.device.brightness)

        # Generate and set button icons
        icon_dir = CACHE_DIR / "icons"
        icon_paths = generate_all_icons(self.config.buttons, icon_dir)
        for key_num, path in icon_paths.items():
            self._device.set_key_image(key_num, path)

        # Set idle LED color
        r, g, b = self.config.device.led_idle_color
        self._device.set_led_color(r, g, b)

        # Register key callback
        self._device.set_key_callback(self._on_key_press)
        self._device.start_listening()

        # Start sync worker
        self.sync_worker.start()

        # Initial dashboard fetch
        self._refresh_dashboard()

        # Start dashboard poll loop
        self._poll_thread = threading.Thread(
            target=self._dashboard_poll_loop,
            daemon=True,
            name="dashboard-poll",
        )
        self._poll_thread.start()

        logger.info("Macropad controller running")

    def stop(self) -> None:
        """Clean shutdown."""
        logger.info("Shutting down macropad controller")
        self._shutdown.set()
        self.sync_worker.stop()
        self._device.close()
        self.api_client.close()
        self.queue.close()
        logger.info("Macropad controller stopped")

    def wait(self) -> None:
        """Block until shutdown is signaled."""
        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(timeout=1.0)
        except KeyboardInterrupt:
            pass

    def _on_key_press(self, key: int, is_pressed: bool) -> None:
        """Handle a key press event from the device."""
        if not is_pressed:
            return  # Only act on press, not release

        button = self.config.buttons.get(key)
        if not button:
            logger.debug("Key %d pressed but not configured", key)
            return

        logger.info("Key %d pressed: %s (%s)", key, button.label, button.action)

        # Flash LED green to acknowledge press
        self._flash_led(0, 255, 0, duration=0.3)

        # Dispatch action
        try:
            self._dispatch_action(button.action, button.params)
            # Success LED
            r, g, b = button.feedback.success_led
            self._flash_led(r, g, b, duration=0.8)
            logger.info("Action succeeded: %s", button.action)
        except (BabyBasicsAPIError, ConnectionError, Exception) as e:
            logger.warning("Action failed, queueing offline: %s", e)
            self.queue.enqueue(button.action, dict(button.params))
            # Amber pulse for queued
            self._flash_led(255, 180, 0, duration=1.5)

        # Refresh dashboard after action
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _dispatch_action(self, action: str, params: dict[str, Any]) -> Any:
        """Route an action string to the appropriate API call."""
        if action == "baby_basics.log_feeding":
            return self.api_client.log_feeding(**params)
        elif action == "baby_basics.log_diaper":
            return self.api_client.log_diaper(**params)
        elif action == "baby_basics.toggle_sleep":
            return self.api_client.toggle_sleep(dashboard=self._dashboard)
        elif action == "baby_basics.log_note":
            return self.api_client.log_note(**params)
        elif action.startswith("home_assistant."):
            logger.info("Home Assistant action: %s (not implemented in Phase 1)", action)
            return None
        else:
            logger.error("Unknown action: %s", action)
            raise ValueError(f"Unknown action: {action}")

    def _refresh_dashboard(self) -> None:
        """Fetch dashboard data and update the touchscreen."""
        try:
            self._dashboard = self.api_client.get_dashboard()
            self._connected = True
            self._update_touchscreen()
        except Exception as e:
            logger.warning("Dashboard refresh failed: %s", e)
            self._connected = False
            self._update_touchscreen()

    def _update_touchscreen(self) -> None:
        """Re-render and push the dashboard image to the device."""
        dash_data = self._dashboard.raw if self._dashboard else None
        dash_path = CACHE_DIR / "dashboard.jpg"
        save_dashboard(
            output_path=dash_path,
            dashboard_data=dash_data,
            connected=self._connected,
            queued_count=self.queue.count(),
        )
        self._device.set_touchscreen_image(dash_path)

    def _dashboard_poll_loop(self) -> None:
        """Poll the dashboard API at the configured interval."""
        interval = self.config.dashboard.poll_interval_seconds
        while not self._shutdown.is_set():
            self._shutdown.wait(interval)
            if not self._shutdown.is_set():
                self._refresh_dashboard()

    def _flash_led(self, r: int, g: int, b: int, duration: float = 0.5) -> None:
        """Flash the LED ring, then return to idle color."""
        def _flash():
            self._device.set_led_color(r, g, b)
            time.sleep(duration)
            ir, ig, ib = self.config.device.led_idle_color
            self._device.set_led_color(ir, ig, ib)

        threading.Thread(target=_flash, daemon=True).start()

    def _on_sync_success(self, event: Any) -> None:
        logger.info("Synced offline event: %s", event.action)
        self._flash_led(0, 255, 0, duration=0.3)

    def _on_sync_failure(self, event: Any, error: str) -> None:
        logger.warning("Failed to sync event %s: %s", event.id[:8], error)


def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("Baby Basics Macropad v0.1.0")

    try:
        config = load_config()
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        sys.exit(1)

    controller = MacropadController(config)

    # Handle signals for clean shutdown
    def _signal_handler(sig: int, frame: Any) -> None:
        logger.info("Received signal %d, shutting down", sig)
        controller.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    controller.start()
    controller.wait()
    controller.stop()


if __name__ == "__main__":
    main()
