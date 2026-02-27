"""Main entry point for the Baby Basics macropad controller.

Mode-aware controller that manages the display state machine:
  home_grid → detail → confirmation → home_grid
  home_grid → sleep_mode → (wake) → confirmation → home_grid
  home_grid → notes_submenu → confirmation → home_grid
  home_grid → settings → home_grid
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any

from baby_macropad.actions.baby_basics import BabyBasicsAPIError, BabyBasicsClient, DashboardData
from baby_macropad.config import MacropadConfig, load_config
from baby_macropad.device import StreamDockDevice, StubDevice
from baby_macropad.offline.queue import OfflineQueue
from baby_macropad.offline.sync import SyncWorker
from baby_macropad.state import DisplayState
from baby_macropad.ui.icons import get_key_grid_bytes

# Renderer imports — individual modules created by the renderer teammate.
try:
    from baby_macropad.ui.detail import render_detail_screen
except ImportError:
    render_detail_screen = None  # type: ignore[assignment]
try:
    from baby_macropad.ui.confirmation import render_confirmation
except ImportError:
    render_confirmation = None  # type: ignore[assignment]
try:
    from baby_macropad.ui.sleep import render_sleep_mode
except ImportError:
    render_sleep_mode = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".baby-macropad" / "cache"

# Confirmation screen duration (seconds)
CONFIRMATION_DURATION = 5.0

# --- Category colors for LED feedback ---
CATEGORY_COLORS = {
    "feeding": (102, 204, 102),    # Soft green
    "diaper": (204, 170, 68),      # Warm amber
    "sleep_start": (102, 153, 204),  # Soft blue
    "sleep_end": (255, 220, 150),  # Warm white
    "note": (153, 153, 153),       # Gray
    "pump": (153, 153, 153),       # Gray
    "undo": (255, 255, 255),       # White
    "queued": (255, 180, 0),       # Amber
    "error": (220, 60, 60),        # Red
    "acknowledge": (255, 255, 255),  # White
}

# --- Detail screen configurations ---
# Maps a detail action key to the options, default, API action, and params.
DETAIL_CONFIGS: dict[str, dict[str, Any]] = {
    "breast_left": {
        "title": "LEFT BREAST",
        "options": [
            {"label": "One Side", "key": 11, "value": {"both_sides": False}},
            {"label": "Both Sides", "key": 12, "value": {"both_sides": True}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102),
        "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "breast", "started_side": "left"},
        "confirmation_label": "Left breast logged",
        "confirmation_icon": "breast_left",
        "resource_type": "feedings",
        "column": 0,
    },
    "breast_right": {
        "title": "RIGHT BREAST",
        "options": [
            {"label": "One Side", "key": 11, "value": {"both_sides": False}},
            {"label": "Both Sides", "key": 12, "value": {"both_sides": True}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102),
        "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "breast", "started_side": "right"},
        "confirmation_label": "Right breast logged",
        "confirmation_icon": "breast_right",
        "resource_type": "feedings",
        "column": 0,
    },
    "bottle": {
        "title": "BOTTLE",
        "options": [
            {"label": "Formula", "key": 11, "value": {"source": "formula"}},
            {"label": "Breast Milk", "key": 12, "value": {"source": "breast_milk"}},
            {"label": "Skip", "key": 13, "value": {}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102),
        "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "bottle"},
        "confirmation_label": "Bottle logged",
        "confirmation_icon": "bottle",
        "resource_type": "feedings",
        "column": 0,
    },
    "poop": {
        "title": "POOP",
        "options": [
            {"label": "Watery", "key": 11, "value": {"consistency": "watery"}},
            {"label": "Loose", "key": 12, "value": {"consistency": "loose"}},
            {"label": "Formed", "key": 13, "value": {"consistency": "formed"}},
            {"label": "Hard", "key": 14, "value": {"consistency": "hard"}},
        ],
        "default_index": 2,  # "Formed" is the default
        "category_color": (204, 170, 68),
        "category": "diaper",
        "api_action": "baby_basics.log_diaper",
        "base_params": {"type": "poop"},
        "confirmation_label": "Poop logged",
        "confirmation_icon": "diaper_poop",
        "resource_type": "diapers",
        "column": 1,
    },
    "both": {
        "title": "PEE + POOP",
        "options": [
            {"label": "Watery", "key": 11, "value": {"consistency": "watery"}},
            {"label": "Loose", "key": 12, "value": {"consistency": "loose"}},
            {"label": "Formed", "key": 13, "value": {"consistency": "formed"}},
            {"label": "Hard", "key": 14, "value": {"consistency": "hard"}},
        ],
        "default_index": 2,
        "category_color": (204, 170, 68),
        "category": "diaper",
        "api_action": "baby_basics.log_diaper",
        "base_params": {"type": "both"},
        "confirmation_label": "Pee + poop logged",
        "confirmation_icon": "diaper_both",
        "resource_type": "diapers",
        "column": 1,
    },
}

# Map button icon names to detail config keys (for buttons that need detail screens)
_ICON_TO_DETAIL: dict[str, str] = {
    "breast_left": "breast_left",
    "breast_right": "breast_right",
    "bottle": "bottle",
    "diaper_poop": "poop",
    "diaper_both": "both",
}

# Instant actions: these icons log immediately without a detail screen
_INSTANT_ACTIONS: set[str] = {"diaper_pee", "pump"}

# Key number to column mapping (for confirmation color fill)
_KEY_TO_COLUMN: dict[int, int] = {
    11: 0, 6: 0, 1: 0,    # Feeding
    12: 1, 7: 1, 2: 1,    # Diaper
    13: 2, 8: 2, 3: 2,    # Sleep/Pump/Notes
    14: 3, 9: 3, 4: 3,    # HA (reserved)
    15: 4, 10: 4, 5: 4,   # System
}


def _in_time_range(now: dt_time, start: dt_time, end: dt_time) -> bool:
    """True if now is within [start, end). Handles midnight wraparound."""
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def _parse_time(s: str) -> dt_time:
    """Parse 'HH:MM' string to datetime.time."""
    h, m = s.split(":")
    return dt_time(int(h), int(m))


class MacropadController:
    """Orchestrates device, API client, offline queue, and UI rendering.

    The controller is mode-aware: key presses are interpreted differently
    depending on the current DisplayState.mode.
    """

    def __init__(self, config: MacropadConfig) -> None:
        self.config = config
        self._shutdown = threading.Event()

        # Display state machine
        self._state = DisplayState(
            timer_seconds=config.settings_menu.timer_duration_seconds,
            skip_breast_detail=config.settings_menu.skip_breast_detail,
            celebration_style=config.settings_menu.celebration_style,
        )

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

        # Cached display state for keepalive
        self._screen_jpeg: bytes | None = None

        # Button debounce: track last press time per key
        self._last_key_press: dict[int, float] = {}
        self._debounce_seconds = 0.3

        # LED flash generation counter — newer flashes cancel older ones
        self._led_flash_gen = 0
        self._led_lock = threading.Lock()

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

        # Render initial home grid
        self.refresh_display()

        # Turn off LED ring
        self._device.turn_off_leds()

        # Register key callback
        self._device.set_key_callback(self._on_key_press)
        self._device.start_listening()

        # Start sync worker
        self.sync_worker.start()

        # Initial dashboard fetch (runs in background, doesn't block startup)
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

        # Start dashboard poll loop
        self._poll_thread = threading.Thread(
            target=self._dashboard_poll_loop,
            daemon=True,
            name="dashboard-poll",
        )
        self._poll_thread.start()

        # Start heartbeat loop (raw CONNECT command to prevent demo mode)
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="device-heartbeat",
        )
        self._heartbeat_thread.start()

        # Start display tick loop (timer expiry, sleep timer, brightness)
        self._tick_thread = threading.Thread(
            target=self._display_tick_loop,
            daemon=True,
            name="display-tick",
        )
        self._tick_thread.start()

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

    # --- Display rendering ---

    def refresh_display(self) -> None:
        """Render the current screen mode and send to device."""
        s = self._state
        now = time.monotonic()

        if s.mode == "sleep_mode":
            if render_sleep_mode is not None:
                # Calculate elapsed minutes from sleep start time
                elapsed_minutes = 0
                start_time_str = ""
                if s.sleep_start_time:
                    try:
                        start = datetime.fromisoformat(
                            s.sleep_start_time.replace("Z", "+00:00")
                        )
                        elapsed = datetime.now(timezone.utc) - start
                        elapsed_minutes = int(elapsed.total_seconds() // 60)
                        start_time_str = start.astimezone().strftime("%-I:%M %p")
                    except (ValueError, TypeError):
                        start_time_str = ""
                jpeg_bytes = render_sleep_mode(
                    elapsed_minutes=elapsed_minutes,
                    start_time_str=start_time_str,
                )
            else:
                jpeg_bytes = get_key_grid_bytes({})
            self._screen_jpeg = jpeg_bytes
            self._device.set_screen_image(jpeg_bytes)
            return

        if s.mode == "confirmation" and now < s.confirmation_expires:
            if render_confirmation is not None:
                jpeg_bytes = render_confirmation(
                    action_label=s.confirmation_label,
                    context_line=s.confirmation_context,
                    icon_name=s.confirmation_icon,
                    category_color=s.confirmation_category_color,
                    celebration_style=s.celebration_style,
                    column_index=s.confirmation_column,
                )
            else:
                jpeg_bytes = get_key_grid_bytes({})
            self._screen_jpeg = jpeg_bytes
            self._device.set_screen_image(jpeg_bytes)
            return

        if s.mode == "detail" and now < s.detail_timer_expires:
            if render_detail_screen is not None:
                config = DETAIL_CONFIGS.get(s.detail_action or "")
                # Build options list with selected flag for renderer
                options_for_render = []
                for i, opt in enumerate(s.detail_options):
                    options_for_render.append({
                        "label": opt["label"],
                        "key_num": opt.get("key", 11 + i),
                        "selected": i == s.detail_default_index,
                    })
                jpeg_bytes = render_detail_screen(
                    title=config["title"] if config else "DETAIL",
                    options=options_for_render,
                    timer_seconds=max(0, int(s.detail_timer_expires - now)),
                    category_color=config["category_color"] if config else (200, 200, 200),
                )
            else:
                jpeg_bytes = get_key_grid_bytes({})
            self._screen_jpeg = jpeg_bytes
            self._device.set_screen_image(jpeg_bytes)
            return

        # Default: home_grid (also fallback for expired timers)
        if s.mode != "home_grid":
            s.return_home()

        dashboard = self._state.dashboard
        jpeg_bytes = get_key_grid_bytes(self.config.buttons)
        self._screen_jpeg = jpeg_bytes
        self._device.set_screen_image(jpeg_bytes)

    # --- Key press handling (mode-aware) ---

    def _on_key_press(self, key: int, is_pressed: bool) -> None:
        """Handle a key press event from the device."""
        if not is_pressed:
            return

        # Debounce
        now = time.monotonic()
        last = self._last_key_press.get(key, 0.0)
        if now - last < self._debounce_seconds:
            return
        self._last_key_press[key] = now

        # Immediate acknowledgment LED flash (always, regardless of mode)
        self._flash_led_acknowledge()

        mode = self._state.mode
        logger.info("Key %d pressed (mode=%s)", key, mode)

        if mode == "home_grid":
            self._handle_home_grid_press(key)
        elif mode == "detail":
            self._handle_detail_press(key)
        elif mode == "confirmation":
            self._handle_confirmation_press(key)
        elif mode == "sleep_mode":
            self._handle_sleep_mode_press(key)
        elif mode == "notes_submenu":
            self._handle_notes_submenu_press(key)
        elif mode == "settings":
            self._handle_settings_press(key)

    def _handle_home_grid_press(self, key: int) -> None:
        """Handle key press on the home grid."""
        button = self.config.buttons.get(key)
        if not button:
            logger.debug("Key %d not configured", key)
            return

        logger.info("Home grid: %s (%s)", button.label, button.action)

        # Settings gear
        if button.action == "macropad.settings":
            self._state.mode = "settings"
            self.refresh_display()
            return

        # Notes submenu
        if button.action == "baby_basics.notes_submenu":
            self._state.mode = "notes_submenu"
            self.refresh_display()
            return

        # Sleep toggle
        if button.action == "baby_basics.toggle_sleep":
            self._handle_sleep_toggle()
            return

        # Check if this button needs a detail screen
        detail_key = _ICON_TO_DETAIL.get(button.icon)
        if detail_key:
            # Skip breast detail if configured
            if detail_key in ("breast_left", "breast_right") and self._state.skip_breast_detail:
                self._execute_instant_action(button, key)
                return
            self._enter_detail_screen(detail_key)
            return

        # Instant actions (pee, pump)
        if button.icon in _INSTANT_ACTIONS:
            self._execute_instant_action(button, key)
            return

        # Generic fallback for unknown actions
        self._execute_instant_action(button, key)

    def _handle_detail_press(self, key: int) -> None:
        """Handle key press on a detail screen."""
        # Key 1 (bottom-left) = Back / Cancel — consistent escape key across all screens
        if key == 1:
            logger.info("Detail: back/cancel")
            self._state.return_home()
            self.refresh_display()
            return

        # Check if the key matches one of the option keys (top row: 11-14)
        config = DETAIL_CONFIGS.get(self._state.detail_action or "")
        if not config:
            self._state.return_home()
            self.refresh_display()
            return

        for i, option in enumerate(config["options"]):
            if key == option["key"]:
                logger.info("Detail: selected option %d (%s)", i, option["label"])
                self._commit_detail_option(config, option)
                return

        # All other keys ignored on detail screen
        logger.debug("Detail: key %d ignored", key)

    def _handle_confirmation_press(self, key: int) -> None:
        """Handle key press on the confirmation screen."""
        # Key 1 (bottom-left) = UNDO
        if key == 1 and self._state.confirmation_resource_id:
            logger.info("Confirmation: UNDO pressed")
            self._execute_undo()
            return

        # All other keys ignored during confirmation
        logger.debug("Confirmation: key %d ignored", key)

    def _handle_sleep_mode_press(self, key: int) -> None:
        """Handle key press during sleep mode."""
        # Wake the screen on any press
        self._device.set_brightness(self.config.device.brightness)

        # Key 13 (Sleep position, col 2 top) = WAKE UP
        if key == 13:
            logger.info("Sleep mode: WAKE UP pressed")
            self._handle_wake_up()
            return

        # All other keys just wake the screen, reset idle timer
        logger.debug("Sleep mode: key %d woke screen only", key)
        self.refresh_display()

    def _handle_notes_submenu_press(self, key: int) -> None:
        """Handle key press on the notes submenu."""
        # Key 1 (bottom-left) = Back — consistent escape key across all screens
        if key == 1:
            logger.info("Notes submenu: back")
            self._state.return_home()
            self.refresh_display()
            return

        # Map keys to note categories (key 1 reserved for Back)
        categories = self.config.notes_categories
        # Top row first, then mid, then bottom (skip key 1 = Back, key 5 = unused)
        option_keys = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 2, 3, 4, 5]
        for i, cat in enumerate(categories):
            if i >= len(option_keys):
                break
            if key == option_keys[i]:
                logger.info("Notes submenu: selected '%s'", cat.label)
                content = cat.content or cat.label
                self._execute_note_action(content, cat.label)
                return

        logger.debug("Notes submenu: key %d ignored", key)

    def _handle_settings_press(self, key: int) -> None:
        """Handle key press on the settings menu."""
        # Key 1 (bottom-left) = Back — consistent escape key across all screens
        if key == 1:
            logger.info("Settings: back to home")
            self._state.return_home()
            self.refresh_display()
            return

        # TODO: implement individual settings controls (timer cycle, skip breast toggle, etc.)
        logger.debug("Settings: key %d (not yet implemented)", key)

    # --- Action execution ---

    def _enter_detail_screen(self, detail_key: str) -> None:
        """Enter a detail screen for the given action."""
        config = DETAIL_CONFIGS.get(detail_key)
        if not config:
            logger.error("No detail config for: %s", detail_key)
            return

        timer_seconds = self._state.timer_seconds
        expires = time.monotonic() + timer_seconds if timer_seconds > 0 else float("inf")

        self._state.enter_detail(
            action=detail_key,
            options=config["options"],
            default_index=config["default_index"],
            context=dict(config["base_params"]),
            timer_expires=expires,
        )
        self.refresh_display()
        logger.info("Entered detail screen: %s (timer=%ds)", detail_key, timer_seconds)

    def _commit_detail_option(self, config: dict[str, Any], option: dict[str, Any]) -> None:
        """Commit a detail screen selection: merge params, call API, show confirmation."""
        params = dict(config["base_params"])
        params.update(option.get("value", {}))

        self._call_api_and_confirm(
            api_action=config["api_action"],
            params=params,
            label=config["confirmation_label"],
            icon=config["confirmation_icon"],
            category_color=config["category_color"],
            category=config["category"],
            column=config["column"],
            resource_type=config["resource_type"],
        )

    def _commit_detail_default(self) -> None:
        """Auto-commit the detail screen with the default option (timer expired)."""
        config = DETAIL_CONFIGS.get(self._state.detail_action or "")
        if not config:
            self._state.return_home()
            self.refresh_display()
            return

        default_option = config["options"][config["default_index"]]
        logger.info("Detail timer expired, auto-committing default: %s", default_option["label"])
        self._commit_detail_option(config, default_option)

    def _execute_instant_action(self, button: Any, key: int) -> None:
        """Execute an instant action (no detail screen) and show confirmation."""
        action = button.action
        params = dict(button.params)
        column = _KEY_TO_COLUMN.get(key, 0)

        # Determine category and confirmation text from button icon
        icon_name = button.icon
        if icon_name == "diaper_pee":
            category = "diaper"
            label = "Pee logged"
            resource_type = "diapers"
        elif icon_name == "pump":
            category = "pump"
            label = "Pump logged"
            resource_type = "notes"
        else:
            category = "feeding"
            label = f"{button.label} logged"
            resource_type = "feedings"

        category_color = CATEGORY_COLORS.get(category, (200, 200, 200))

        self._call_api_and_confirm(
            api_action=action,
            params=params,
            label=label,
            icon=icon_name,
            category_color=category_color,
            category=category,
            column=column,
            resource_type=resource_type,
        )

    def _execute_note_action(self, content: str, label: str) -> None:
        """Log a note from the notes submenu."""
        self._call_api_and_confirm(
            api_action="baby_basics.log_note",
            params={"content": content},
            label=f"{label} logged",
            icon="note",
            category_color=CATEGORY_COLORS["note"],
            category="note",
            column=2,
            resource_type="notes",
        )

    def _call_api_and_confirm(
        self,
        api_action: str,
        params: dict[str, Any],
        label: str,
        icon: str,
        category_color: tuple[int, int, int],
        category: str,
        column: int,
        resource_type: str,
    ) -> None:
        """Call the API, handle success/failure, and enter confirmation screen."""
        resource_id = None
        context_line = ""
        queued = False

        try:
            result = self._dispatch_action(api_action, params)
            # Extract resource ID from API response for UNDO
            if isinstance(result, dict):
                # API wraps single resources: {feeding: {id: ...}}, {diaper: {id: ...}}, etc.
                for key in (resource_type[:-1], resource_type):  # singular, then plural
                    if key in result and isinstance(result[key], dict):
                        resource_id = result[key].get("id")
                        break
                if not resource_id:
                    resource_id = result.get("id")

            # Build context line from dashboard
            context_line = self._build_context_line(category)

            # Category-specific LED feedback
            self._flash_led_category(category)
            logger.info("Action succeeded: %s → %s", api_action, resource_id)

        except (BabyBasicsAPIError, ConnectionError, Exception) as e:
            logger.warning("Action failed, queueing offline: %s", e)
            self.queue.enqueue(api_action, params)
            queued = True
            context_line = "Queued — will sync when connected"
            self._flash_led_queued()

        # Track for undo
        if resource_id:
            self._state.push_recent_action({
                "resource_id": resource_id,
                "resource_type": resource_type,
                "label": label,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # Enter confirmation screen
        self._state.enter_confirmation(
            action=api_action,
            label=label,
            context=context_line,
            icon=icon,
            category_color=category_color,
            column=column,
            expires=time.monotonic() + CONFIRMATION_DURATION,
            resource_id=resource_id,
            resource_type=resource_type,
        )
        self.refresh_display()

        # Refresh dashboard after action (in background)
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _build_context_line(self, category: str) -> str:
        """Build the second line for the confirmation screen from dashboard data."""
        dashboard = self._state.dashboard
        if not isinstance(dashboard, DashboardData):
            return ""

        counts = dashboard.today_counts
        if category == "feeding":
            side = dashboard.suggested_side
            if side:
                return f"Next: {side.capitalize()} breast"
            total = counts.get("feedings", 0)
            return f"{total} feeds today"
        elif category == "diaper":
            total = counts.get("diapers", 0)
            return f"{total} diapers today"
        elif category == "pump":
            return "Pumping session logged"
        elif category == "note":
            return ""
        return ""

    # --- Sleep ---

    def _handle_sleep_toggle(self) -> None:
        """Handle the sleep toggle button on home grid."""
        dashboard = self._state.dashboard

        # Check if sleep is already active (from dashboard data)
        active_sleep = None
        if isinstance(dashboard, DashboardData) and dashboard.active_sleep:
            active_sleep = dashboard.active_sleep

        if active_sleep:
            # Sleep is active on the home grid — this means we previously
            # returned from sleep mode or the app started with active sleep.
            # End the sleep.
            sleep_id = active_sleep.get("id")
            if sleep_id:
                self._end_sleep(sleep_id)
            return

        # Start sleep
        try:
            result = self.api_client.start_sleep()
            sleep_data = result.get("sleep", result)
            sleep_id = sleep_data.get("id", "")
            start_time = sleep_data.get("start_time", datetime.now(timezone.utc).isoformat())

            self._state.enter_sleep_mode(sleep_id=sleep_id, start_time=start_time)

            # LED: blue pulses for sleep start
            self._flash_led_sleep_start()

            # Dim screen
            self._device.set_brightness(10)
            self.refresh_display()

            logger.info("Sleep started: %s", sleep_id)
        except (BabyBasicsAPIError, ConnectionError, Exception) as e:
            logger.warning("Failed to start sleep: %s", e)
            self.queue.enqueue("baby_basics.toggle_sleep", {})
            self._flash_led_queued()

    def _handle_wake_up(self) -> None:
        """End the active sleep from sleep mode."""
        sleep_id = self._state.sleep_id
        if not sleep_id:
            logger.warning("Wake up pressed but no sleep_id in state")
            self._state.return_home()
            self.refresh_display()
            return

        self._end_sleep(sleep_id)

    def _end_sleep(self, sleep_id: str) -> None:
        """End a sleep session and show wake-up confirmation."""
        # Restore brightness
        self._device.set_brightness(self.config.device.brightness)

        try:
            result = self.api_client.end_sleep(sleep_id)

            # Calculate sleep duration for display
            start_time = self._state.sleep_start_time
            duration_str = ""
            if start_time:
                try:
                    start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    elapsed = datetime.now(timezone.utc) - start
                    hours = int(elapsed.total_seconds() // 3600)
                    minutes = int((elapsed.total_seconds() % 3600) // 60)
                    if hours > 0:
                        duration_str = f"Slept {hours}h {minutes}m"
                    else:
                        duration_str = f"Slept {minutes}m"
                except (ValueError, TypeError):
                    duration_str = "Sleep ended"

            self._state.exit_sleep_mode()

            # LED: warm white burst for wake up
            self._flash_led_wake()

            # Show wake-up confirmation
            self._state.enter_confirmation(
                action="baby_basics.end_sleep",
                label="Baby's awake!",
                context=duration_str,
                icon="sunrise",
                category_color=(255, 220, 150),
                column=2,
                expires=time.monotonic() + CONFIRMATION_DURATION,
                resource_id=None,  # No UNDO on wake-up
                resource_type="sleeps",
            )
            self.refresh_display()

            logger.info("Sleep ended: %s (%s)", sleep_id, duration_str)

        except (BabyBasicsAPIError, ConnectionError, Exception) as e:
            logger.warning("Failed to end sleep: %s", e)
            self._state.exit_sleep_mode()
            self._state.return_home()
            self.refresh_display()
            self._flash_led_error()

        # Refresh dashboard
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    # --- UNDO ---

    def _execute_undo(self) -> None:
        """Delete the most recently logged resource (UNDO)."""
        resource_id = self._state.confirmation_resource_id
        resource_type = self._state.confirmation_resource_type

        if not resource_id or not resource_type:
            self._state.return_home()
            self.refresh_display()
            return

        logger.info("Undo: DELETE %s/%s", resource_type, resource_id)

        try:
            self._delete_resource(resource_type, resource_id)
            self._flash_led_undo()
            logger.info("Undo successful")
        except Exception as e:
            logger.warning("Undo failed, queueing: %s", e)
            self.queue.enqueue(
                f"baby_basics.delete_{resource_type}",
                {"resource_id": resource_id},
            )
            self._flash_led_queued()

        # Remove from recent actions
        self._state.recent_actions = [
            a for a in self._state.recent_actions
            if a.get("resource_id") != resource_id
        ]

        self._state.return_home()
        self.refresh_display()

        # Refresh dashboard
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _delete_resource(self, resource_type: str, resource_id: str) -> None:
        """DELETE /children/:childId/{resource_type}/:id"""
        resp = self.api_client._client.delete(f"/{resource_type}/{resource_id}")
        if resp.status_code >= 400 and resp.status_code != 204:
            raise BabyBasicsAPIError(resp.status_code, resp.text)

    # --- Action dispatch ---

    def _dispatch_action(self, action: str, params: dict[str, Any]) -> Any:
        """Route an action string to the appropriate API call."""
        if action == "baby_basics.log_feeding":
            return self.api_client.log_feeding(**params)
        elif action == "baby_basics.log_diaper":
            return self.api_client.log_diaper(**params)
        elif action == "baby_basics.toggle_sleep":
            return self.api_client.toggle_sleep(dashboard=self._state.dashboard)
        elif action == "baby_basics.log_note":
            return self.api_client.log_note(**params)
        elif action.startswith("home_assistant."):
            logger.info("Home Assistant action: %s (not implemented in Phase 1)", action)
            return None
        else:
            logger.error("Unknown action: %s", action)
            raise ValueError(f"Unknown action: {action}")

    # --- Dashboard ---

    def _refresh_dashboard(self) -> None:
        """Fetch dashboard data and update state."""
        try:
            dashboard = self.api_client.get_dashboard()
            self._state.dashboard = dashboard
            self._state.connected = True
            self._state.queued_count = self.queue.count()

            # If dashboard shows active sleep but we're on home grid, update state
            if (
                dashboard.active_sleep
                and not self._state.sleep_active
                and self._state.mode == "home_grid"
            ):
                self._state.sleep_active = True
                self._state.sleep_id = dashboard.active_sleep.get("id")
                self._state.sleep_start_time = dashboard.active_sleep.get("start_time")

            logger.info("Dashboard refreshed")
        except Exception as e:
            logger.warning("Dashboard refresh failed: %s", e)
            self._state.connected = False

    def _dashboard_poll_loop(self) -> None:
        """Poll the dashboard API at the configured interval."""
        interval = self.config.dashboard.poll_interval_seconds
        while not self._shutdown.is_set():
            self._shutdown.wait(interval)
            if not self._shutdown.is_set():
                self._refresh_dashboard()

    # --- Display tick loop ---

    def _display_tick_loop(self) -> None:
        """1-second tick for timer countdown, auto-dismiss, and display updates."""
        while not self._shutdown.is_set():
            self._shutdown.wait(1)
            if self._shutdown.is_set():
                break

            now = time.monotonic()
            s = self._state

            # Confirmation auto-dismiss
            if s.mode == "confirmation" and now >= s.confirmation_expires:
                logger.info("Confirmation expired, returning to home")
                s.return_home()
                self.refresh_display()
                continue

            # Detail screen: refresh countdown every tick, auto-commit on expiry
            if s.mode == "detail":
                if s.detail_timer_expires > 0 and now >= s.detail_timer_expires:
                    logger.info("Detail timer expired")
                    self._commit_detail_default()
                else:
                    self.refresh_display()
                continue

            # Sleep mode: update elapsed timer display (every tick)
            if s.mode == "sleep_mode":
                self.refresh_display()
                continue

            # Brightness schedule check (only on home_grid, once per tick)
            self._check_brightness_schedule()

    def _check_brightness_schedule(self) -> None:
        """Apply brightness schedule if enabled."""
        schedule = self.config.display.brightness_schedule
        if not schedule.enabled:
            return

        now_time = datetime.now().time()
        night_start = _parse_time(schedule.night_start)
        night_end = _parse_time(schedule.night_end)

        if _in_time_range(now_time, night_start, night_end):
            self._device.set_brightness(schedule.night_brightness)
        else:
            self._device.set_brightness(schedule.day_brightness)

    # --- Heartbeat ---

    def _heartbeat_loop(self) -> None:
        """Send raw CONNECT heartbeat to prevent firmware demo mode."""
        while not self._shutdown.is_set():
            self._shutdown.wait(10)
            if self._shutdown.is_set():
                break
            self._device.send_heartbeat()

    # --- LED feedback ---

    def _flash_led_acknowledge(self) -> None:
        """Immediate white flash on any key press (150ms)."""
        r, g, b = CATEGORY_COLORS["acknowledge"]
        self._flash_led(r, g, b, brightness=60, duration=0.15)

    def _flash_led_category(self, category: str) -> None:
        """Flash the LED ring in the category color."""
        if category == "feeding":
            r, g, b = CATEGORY_COLORS["feeding"]
            self._flash_led(r, g, b, brightness=65, duration=0.6)
        elif category == "diaper":
            r, g, b = CATEGORY_COLORS["diaper"]
            self._flash_led(r, g, b, brightness=65, duration=0.6)
        elif category in ("pump", "note"):
            r, g, b = CATEGORY_COLORS["note"]
            self._flash_led(r, g, b, brightness=50, duration=0.4)

    def _flash_led_sleep_start(self) -> None:
        """Blue triple pulse for sleep start."""
        with self._led_lock:
            self._led_flash_gen += 1
            my_gen = self._led_flash_gen

        def _pulse():
            r, g, b = CATEGORY_COLORS["sleep_start"]
            for _ in range(3):
                self._device.set_led_brightness(50)
                self._device.set_led_color(r, g, b)
                time.sleep(0.3)
                self._device.turn_off_leds()
                time.sleep(0.2)
        threading.Thread(target=_pulse, daemon=True).start()

    def _flash_led_wake(self) -> None:
        """Warm white burst for wake up."""
        with self._led_lock:
            self._led_flash_gen += 1

        def _burst():
            r, g, b = CATEGORY_COLORS["sleep_end"]
            self._device.set_led_brightness(100)
            self._device.set_led_color(r, g, b)
            time.sleep(0.4)
            for level in (80, 60, 40, 20, 0):
                self._device.set_led_brightness(level)
                time.sleep(0.12)
            self._device.turn_off_leds()
        threading.Thread(target=_burst, daemon=True).start()

    def _flash_led_queued(self) -> None:
        """Amber triple beat for queued/offline."""
        with self._led_lock:
            self._led_flash_gen += 1

        def _beat():
            r, g, b = CATEGORY_COLORS["queued"]
            for _ in range(3):
                self._device.set_led_brightness(55)
                self._device.set_led_color(r, g, b)
                time.sleep(0.5)
                self._device.turn_off_leds()
                time.sleep(0.3)
        threading.Thread(target=_beat, daemon=True).start()

    def _flash_led_error(self) -> None:
        """Red triple flash for error."""
        with self._led_lock:
            self._led_flash_gen += 1

        def _flash():
            r, g, b = CATEGORY_COLORS["error"]
            for _ in range(3):
                self._device.set_led_brightness(80)
                self._device.set_led_color(r, g, b)
                time.sleep(0.2)
                self._device.turn_off_leds()
                time.sleep(0.1)
        threading.Thread(target=_flash, daemon=True).start()

    def _flash_led_undo(self) -> None:
        """White flash for undo."""
        r, g, b = CATEGORY_COLORS["undo"]
        self._flash_led(r, g, b, brightness=65, duration=0.3)

    def _flash_led(
        self, r: int, g: int, b: int, brightness: int = 50, duration: float = 0.5
    ) -> None:
        """Flash the LED ring with a single color, then turn off.

        Uses a generation counter so newer flashes cancel older ones —
        prevents the acknowledge flash from killing the category flash.
        """
        with self._led_lock:
            self._led_flash_gen += 1
            my_gen = self._led_flash_gen

        def _do_flash():
            self._device.set_led_brightness(brightness)
            self._device.set_led_color(r, g, b)
            time.sleep(duration)
            # Only turn off if no newer flash has started
            with self._led_lock:
                if self._led_flash_gen == my_gen:
                    self._device.turn_off_leds()
        threading.Thread(target=_do_flash, daemon=True).start()

    # --- Sync callbacks ---

    def _on_sync_success(self, event: Any) -> None:
        logger.info("Synced offline event: %s", event.action)
        self._state.queued_count = self.queue.count()
        self._flash_led(0, 255, 0, duration=0.3)

    def _on_sync_failure(self, event: Any, error: str) -> None:
        logger.warning("Failed to sync event %s: %s", event.id[:8], error)
        self._state.queued_count = self.queue.count()


def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("Baby Basics Macropad v0.2.0")

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
