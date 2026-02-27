"""Main entry point for the Baby Basics macropad controller.

Thin orchestrator that wires together:
  - StateMachine (thread-safe state)
  - KeyRouter (declarative key→action mapping)
  - LedController (LED ring animations)
  - Screen factories + ScreenRenderer (declarative UI)
  - BabyBasicsClient (API calls)
  - OfflineQueue + SyncWorker (offline resilience)
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from datetime import datetime, time as dt_time, timezone
from typing import Any

from baby_macropad.actions.baby_basics import BabyBasicsAPIError, BabyBasicsClient, DashboardData
from baby_macropad.config import MacropadConfig, load_config
from baby_macropad.device import StreamDockDevice, StubDevice
from baby_macropad.offline.queue import OfflineQueue
from baby_macropad.offline.sync import SyncWorker
from baby_macropad.state import DisplayState
from baby_macropad.ui.framework.screen import ScreenRenderer
from baby_macropad.ui.key_router import KeyRouter
from baby_macropad.ui.led import LedController
from baby_macropad.ui.state_machine import StateMachine
from baby_macropad.ui.screens.home import build_home_grid
from baby_macropad.ui.screens.detail import build_detail_screen
from baby_macropad.ui.screens.confirmation import build_confirmation_screen
from baby_macropad.ui.screens.selection import build_selection_screen
from baby_macropad.ui.screens.settings_screen import build_settings_screen
from baby_macropad.ui.screens.sleep_screen import build_sleep_screen
from baby_macropad.ui.screens.dashboard_screen import build_dashboard_screen
from baby_macropad.settings import SettingsModel

logger = logging.getLogger(__name__)

CONFIRMATION_DURATION = 5.0

# Detail screen configurations (maps action key → options, API action, params)
DETAIL_CONFIGS: dict[str, dict[str, Any]] = {
    "breast_left": {
        "title": "LEFT BREAST",
        "options": [
            {"label": "One", "key": 11, "value": {"both_sides": False}},
            {"label": "Both", "key": 12, "value": {"both_sides": True}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102), "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "breast", "started_side": "left"},
        "confirmation_label": "Fed L", "confirmation_icon": "breast_left",
        "resource_type": "feedings", "column": 0,
    },
    "breast_right": {
        "title": "RIGHT BREAST",
        "options": [
            {"label": "One", "key": 11, "value": {"both_sides": False}},
            {"label": "Both", "key": 12, "value": {"both_sides": True}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102), "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "breast", "started_side": "right"},
        "confirmation_label": "Fed R", "confirmation_icon": "breast_right",
        "resource_type": "feedings", "column": 0,
    },
    "bottle": {
        "title": "BOTTLE",
        "options": [
            {"label": "Formula", "key": 11, "value": {"source": "formula"}},
            {"label": "Brst Milk", "key": 12, "value": {"source": "breast_milk"}},
            {"label": "Skip", "key": 13, "value": {}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102), "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "bottle"},
        "confirmation_label": "Bottle", "confirmation_icon": "bottle",
        "resource_type": "feedings", "column": 0,
    },
    "poop": {
        "title": "POOP",
        "options": [
            {"label": "Watery", "key": 11, "value": {"consistency": "watery"}},
            {"label": "Loose", "key": 12, "value": {"consistency": "loose"}},
            {"label": "Formed", "key": 13, "value": {"consistency": "formed"}},
            {"label": "Hard", "key": 14, "value": {"consistency": "hard"}},
        ],
        "default_index": 2,
        "category_color": (204, 170, 68), "category": "diaper",
        "api_action": "baby_basics.log_diaper",
        "base_params": {"type": "poop"},
        "confirmation_label": "Poop", "confirmation_icon": "diaper_poop",
        "resource_type": "diapers", "column": 1,
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
        "category_color": (204, 170, 68), "category": "diaper",
        "api_action": "baby_basics.log_diaper",
        "base_params": {"type": "both"},
        "confirmation_label": "Pee+Poop", "confirmation_icon": "diaper_both",
        "resource_type": "diapers", "column": 1,
    },
}

_ICON_TO_DETAIL: dict[str, str] = {
    "breast_left": "breast_left", "breast_right": "breast_right",
    "bottle": "bottle", "diaper_poop": "poop", "diaper_both": "both",
}
_INSTANT_ACTIONS: set[str] = {"diaper_pee"}
_KEY_TO_COLUMN: dict[int, int] = {
    11: 0, 6: 0, 1: 0, 12: 1, 7: 1, 2: 1, 13: 2, 8: 2, 3: 2,
    14: 3, 9: 3, 4: 3, 15: 4, 10: 4, 5: 4,
}


def _in_time_range(now: dt_time, start: dt_time, end: dt_time) -> bool:
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def _parse_time(s: str) -> dt_time:
    h, m = s.split(":")
    return dt_time(int(h), int(m))


class MacropadController:
    """Orchestrates device, API client, offline queue, and UI rendering."""

    def __init__(self, config: MacropadConfig) -> None:
        self.config = config
        self._shutdown = threading.Event()

        # State machine (thread-safe)
        self._sm = StateMachine(DisplayState(
            timer_seconds=config.settings_menu.timer_duration_seconds,
            skip_breast_detail=config.settings_menu.skip_breast_detail,
            celebration_style=config.settings_menu.celebration_style,
        ))

        # Settings model
        self._settings = SettingsModel.load()

        # API client
        self.api_client = BabyBasicsClient(
            api_url=config.baby_basics.api_url,
            token=config.baby_basics.token,
            child_id=config.baby_basics.child_id,
        )

        # Offline queue
        self.queue = OfflineQueue()
        self.sync_worker = SyncWorker(
            queue=self.queue, api_client=self.api_client,
            on_sync_success=self._on_sync_success,
            on_sync_failure=self._on_sync_failure,
        )

        # Rendering
        self._renderer = ScreenRenderer()
        self._router = KeyRouter()

        # Device
        self._device = StreamDockDevice()

        # LED controller (set after device init)
        self._led = LedController(self._device)

    def start(self) -> None:
        logger.info("Starting macropad controller")
        if not self._device.open():
            logger.info("Using stub device (no hardware found)")
            self._device = StubDevice()
            self._device.open()
            self._led = LedController(self._device)

        self._device.set_brightness(self.config.device.brightness)
        self.refresh_display()
        self._device.turn_off_leds()
        self._device.set_key_callback(self._on_key_press)
        self._device.start_listening()
        self.sync_worker.start()
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

        for name, target in [
            ("dashboard-poll", self._dashboard_poll_loop),
            ("device-heartbeat", self._heartbeat_loop),
            ("display-tick", self._display_tick_loop),
        ]:
            threading.Thread(target=target, daemon=True, name=name).start()

        logger.info("Macropad controller running")

    def stop(self) -> None:
        logger.info("Shutting down macropad controller")
        self._shutdown.set()
        self.sync_worker.stop()
        self._device.close()
        self.api_client.close()
        self.queue.close()

    def wait(self) -> None:
        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(timeout=1.0)
        except KeyboardInterrupt:
            pass

    # --- Display ---

    def refresh_display(self) -> None:
        s = self._sm.state
        now = time.monotonic()

        if s.mode == "sleep_mode":
            elapsed, start_str = self._calc_sleep_elapsed()
            screen = build_sleep_screen(elapsed, start_str)
        elif s.mode == "confirmation" and now < s.confirmation_expires:
            screen = build_confirmation_screen(
                s.confirmation_label, s.confirmation_context,
                s.confirmation_icon, s.confirmation_category_color,
                s.celebration_style, s.confirmation_column,
            )
        elif s.mode == "detail" and now < s.detail_timer_expires:
            cfg = DETAIL_CONFIGS.get(s.detail_action or "")
            opts = [{"label": o["label"], "key_num": o.get("key", 11 + i), "selected": i == s.detail_default_index}
                    for i, o in enumerate(s.detail_options)]
            screen = build_detail_screen(
                cfg["title"] if cfg else "DETAIL", opts,
                max(0, int(s.detail_timer_expires - now)),
                cfg["category_color"] if cfg else (200, 200, 200),
            )
        elif s.mode == "notes_submenu":
            cats = [{"label": c.label, "icon": getattr(c, "icon", None)} for c in self.config.notes_categories]
            screen = build_selection_screen(cats, accent_color=(153, 153, 153))
        elif s.mode == "settings":
            screen = build_settings_screen(self._settings)
        else:
            if s.mode != "home_grid":
                self._sm.return_home()
            runtime_state = self._build_runtime_state()
            screen = build_home_grid(self.config.buttons, runtime_state)

        self._router.set_screen(screen)
        jpeg = self._renderer.render(screen)
        self._device.set_screen_image(jpeg)

    def _calc_sleep_elapsed(self) -> tuple[int, str]:
        start_time = self._sm.get_sleep_start_time()
        if not start_time:
            return 0, ""
        try:
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            elapsed = int((datetime.now(timezone.utc) - start).total_seconds() // 60)
            return elapsed, start.astimezone().strftime("%-I:%M %p")
        except (ValueError, TypeError):
            return 0, ""

    def _build_runtime_state(self) -> dict[int, str]:
        """Build runtime_state overlay for home grid buttons."""
        rs: dict[int, str] = {}
        s = self._sm.state
        # Active sleep overlay
        if s.sleep_active and s.sleep_start_time:
            elapsed, _ = self._calc_sleep_elapsed()
            if elapsed >= 60:
                elapsed_str = f"{elapsed // 60}h {elapsed % 60}m"
            else:
                elapsed_str = f"{elapsed}m"
            for key_num, btn in self.config.buttons.items():
                if btn.icon == "sleep":
                    rs[key_num] = f"active:{elapsed_str}"
        # Suggested breast side
        dashboard = s.dashboard
        if isinstance(dashboard, DashboardData) and dashboard.suggested_side:
            suggested = dashboard.suggested_side  # "left" or "right"
            for key_num, btn in self.config.buttons.items():
                if btn.icon == f"breast_{suggested}":
                    rs[key_num] = "suggested"
        return rs

    # --- Key handling ---

    def _on_key_press(self, key: int, is_pressed: bool) -> None:
        if not is_pressed:
            return

        snap = self._sm.try_handle_key(key)
        if snap is None:
            return  # debounced

        self._led.flash_acknowledge()
        logger.info("Key %d pressed (mode=%s)", key, snap.mode)

        if snap.mode == "home_grid":
            self._handle_home_grid_press(key)
        elif snap.mode == "detail":
            self._handle_detail_press(key)
        elif snap.mode == "confirmation":
            self._handle_confirmation_press(key, snap)
        elif snap.mode == "sleep_mode":
            self._handle_sleep_mode_press(key)
        elif snap.mode == "notes_submenu":
            self._handle_notes_submenu_press(key)
        elif snap.mode == "settings":
            self._handle_settings_press(key)

    def _handle_home_grid_press(self, key: int) -> None:
        button = self.config.buttons.get(key)
        if not button:
            return
        if button.action == "macropad.settings":
            self._sm.state.mode = "settings"
            self.refresh_display()
        elif button.action == "baby_basics.notes_submenu":
            self._sm.state.mode = "notes_submenu"
            self.refresh_display()
        elif button.action == "baby_basics.toggle_sleep":
            self._handle_sleep_toggle()
        elif (detail_key := _ICON_TO_DETAIL.get(button.icon)):
            if detail_key in ("breast_left", "breast_right") and self._sm.state.skip_breast_detail:
                self._execute_instant_action(button, key)
            else:
                self._enter_detail_screen(detail_key)
        else:
            self._execute_instant_action(button, key)

    def _handle_detail_press(self, key: int) -> None:
        if key == 1:
            self._sm.return_home()
            self.refresh_display()
            return
        cfg = DETAIL_CONFIGS.get(self._sm.get_detail_action() or "")
        if not cfg:
            self._sm.return_home()
            self.refresh_display()
            return
        for i, opt in enumerate(cfg["options"]):
            if key == opt["key"]:
                self._commit_detail_option(cfg, opt)
                return

    def _handle_confirmation_press(self, key: int, snap: Any) -> None:
        if key == 1 and snap.state.confirmation_resource_id:
            self._execute_undo()
            return
        # Pressing any key during confirmation dismisses it early
        self._sm.return_home()
        self.refresh_display()

    def _handle_sleep_mode_press(self, key: int) -> None:
        self._device.set_brightness(self.config.device.brightness)
        if key == 13:
            self._handle_wake_up()
        else:
            self.refresh_display()

    def _handle_notes_submenu_press(self, key: int) -> None:
        if key == 1:
            self._sm.return_home()
            self.refresh_display()
            return
        option_keys = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 2, 3, 4, 5]
        for i, cat in enumerate(self.config.notes_categories):
            if i >= len(option_keys):
                break
            if key == option_keys[i]:
                self._execute_note_action(cat.content or cat.label, cat.label)
                return

    def _handle_settings_press(self, key: int) -> None:
        if key == 1:
            self._sm.return_home()
            self.refresh_display()
            return
        # Settings cards are at keys 11, 12, 13, 14, 15, 6, 7...
        setting_keys = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10]
        visible_fields = [n for n, f in type(self._settings).model_fields.items()
                          if not (f.json_schema_extra or {}).get("hidden")]
        for i, field_name in enumerate(visible_fields):
            if i < len(setting_keys) and key == setting_keys[i]:
                self._settings.cycle_field(field_name)
                # Sync timer_seconds and other settings to state
                self._sm.state.timer_seconds = self._settings.timer_duration_seconds
                self._sm.state.celebration_style = self._settings.celebration_style
                self._sm.state.skip_breast_detail = self._settings.skip_breast_detail
                # Apply brightness immediately if that's what changed
                self._device.set_brightness(self._settings.brightness)
                self.refresh_display()
                return

    # --- Action execution ---

    def _enter_detail_screen(self, detail_key: str) -> None:
        cfg = DETAIL_CONFIGS.get(detail_key)
        if not cfg:
            return
        timer = self._sm.state.timer_seconds
        expires = time.monotonic() + timer if timer > 0 else float("inf")
        self._sm.enter_detail(detail_key, cfg["options"], cfg["default_index"], dict(cfg["base_params"]), expires)
        self.refresh_display()

    def _commit_detail_option(self, cfg: dict, option: dict) -> None:
        params = dict(cfg["base_params"])
        params.update(option.get("value", {}))
        self._call_api_and_confirm(
            cfg["api_action"], params, cfg["confirmation_label"], cfg["confirmation_icon"],
            cfg["category_color"], cfg["category"], cfg["column"], cfg["resource_type"],
        )

    def _commit_detail_default(self) -> None:
        # Guard: if mode already changed (e.g., user pressed a key), bail out
        if self._sm.mode != "detail":
            return
        cfg = DETAIL_CONFIGS.get(self._sm.get_detail_action() or "")
        if not cfg:
            self._sm.return_home()
            self.refresh_display()
            return
        self._commit_detail_option(cfg, cfg["options"][cfg["default_index"]])

    def _execute_instant_action(self, button: Any, key: int) -> None:
        icon_name = button.icon
        column = _KEY_TO_COLUMN.get(key, 0)
        if icon_name == "diaper_pee":
            cat, label, rtype = "diaper", "Pee", "diapers"
        elif icon_name == "pump":
            cat, label, rtype = "pump", "Pump", "notes"
        else:
            cat, label, rtype = "feeding", button.label, "feedings"
        color = {"feeding": (102, 204, 102), "diaper": (204, 170, 68)}.get(cat, (200, 200, 200))
        self._call_api_and_confirm(button.action, dict(button.params), label, icon_name, color, cat, column, rtype)

    def _execute_note_action(self, content: str, label: str) -> None:
        self._call_api_and_confirm("baby_basics.log_note", {"content": content}, label, "note", (153, 153, 153), "note", 2, "notes")

    def _call_api_and_confirm(self, api_action: str, params: dict, label: str, icon: str,
                              category_color: tuple[int, int, int], category: str, column: int, resource_type: str) -> None:
        resource_id = None
        context_line = ""
        try:
            result = self._dispatch_action(api_action, params)
            if isinstance(result, dict):
                for k in (resource_type[:-1], resource_type):
                    if k in result and isinstance(result[k], dict):
                        resource_id = result[k].get("id")
                        break
                if not resource_id:
                    resource_id = result.get("id")
            context_line = self._build_context_line(category)
            self._led.flash_category(category)
        except (BabyBasicsAPIError, ConnectionError, Exception) as e:
            logger.warning("Action failed, queueing offline: %s", e)
            self.queue.enqueue(api_action, params)
            context_line = "Queued — will sync when connected"
            self._led.flash_queued()

        if resource_id:
            self._sm.push_recent_action({"resource_id": resource_id, "resource_type": resource_type,
                                         "label": label, "timestamp": datetime.now(timezone.utc).isoformat()})
        self._sm.enter_confirmation(api_action, label, context_line, icon, category_color, column,
                                    time.monotonic() + CONFIRMATION_DURATION, resource_id, resource_type)
        self.refresh_display()
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _build_context_line(self, category: str) -> str:
        dashboard = self._sm.state.dashboard
        if not isinstance(dashboard, DashboardData):
            return ""
        counts = dashboard.today_counts
        if category == "feeding":
            side = dashboard.suggested_side
            return f"Next: {side.capitalize()} breast" if side else f"{counts.get('feedings', 0)} feeds today"
        elif category == "diaper":
            return f"{counts.get('diapers', 0)} diapers today"
        elif category == "pump":
            return "Pumping session logged"
        return ""

    # --- Sleep ---

    def _handle_sleep_toggle(self) -> None:
        dashboard = self._sm.state.dashboard
        active = isinstance(dashboard, DashboardData) and dashboard.active_sleep
        if active:
            sleep_id = dashboard.active_sleep.get("id")
            if sleep_id:
                self._end_sleep(sleep_id)
            return
        try:
            result = self.api_client.start_sleep()
            data = result.get("sleep", result)
            self._sm.enter_sleep_mode(data.get("id", ""), data.get("start_time", datetime.now(timezone.utc).isoformat()))
            self._led.flash_sleep_start()
        except (BabyBasicsAPIError, ConnectionError, Exception) as e:
            logger.warning("Failed to start sleep: %s", e)
            self.queue.enqueue("baby_basics.toggle_sleep", {})
            self._sm.enter_sleep_mode("pending", datetime.now(timezone.utc).isoformat())
            self._led.flash_queued()
        self._device.set_brightness(10)
        self.refresh_display()

    def _handle_wake_up(self) -> None:
        sleep_id = self._sm.get_sleep_id()
        if not sleep_id:
            self._sm.return_home()
            self.refresh_display()
            return
        self._end_sleep(sleep_id)

    def _end_sleep(self, sleep_id: str) -> None:
        self._device.set_brightness(self.config.device.brightness)
        try:
            self.api_client.end_sleep(sleep_id)
            start_time = self._sm.get_sleep_start_time()
            duration_str = self._calc_duration_str(start_time)
            self._sm.exit_sleep_mode()
            self._led.flash_wake()
            self._sm.enter_confirmation("baby_basics.end_sleep", "Awake!", duration_str,
                                        "sunrise", (255, 220, 150), 2, time.monotonic() + CONFIRMATION_DURATION, None, "sleeps")
        except (BabyBasicsAPIError, ConnectionError, Exception) as e:
            logger.warning("Failed to end sleep: %s", e)
            self._sm.exit_sleep_mode()
            self._sm.return_home()
            self._led.flash_error()
        self.refresh_display()
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _calc_duration_str(self, start_time: str | None) -> str:
        if not start_time:
            return "Sleep ended"
        try:
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            secs = (datetime.now(timezone.utc) - start).total_seconds()
            h, m = int(secs // 3600), int((secs % 3600) // 60)
            return f"Slept {h}h {m}m" if h > 0 else f"Slept {m}m"
        except (ValueError, TypeError):
            return "Sleep ended"

    # --- Undo ---

    def _execute_undo(self) -> None:
        rid = self._sm.get_confirmation_resource_id()
        rtype = self._sm.get_confirmation_resource_type()
        if not rid or not rtype:
            self._sm.return_home()
            self.refresh_display()
            return
        try:
            self._delete_resource(rtype, rid)
            self._led.flash_undo()
        except Exception as e:
            logger.warning("Undo failed, queueing: %s", e)
            self.queue.enqueue(f"baby_basics.delete_{rtype}", {"resource_id": rid})
            self._led.flash_queued()
        self._sm.remove_recent_action(rid)
        self._sm.return_home()
        self.refresh_display()
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _delete_resource(self, resource_type: str, resource_id: str) -> None:
        resp = self.api_client._client.delete(f"/{resource_type}/{resource_id}")
        if resp.status_code >= 400 and resp.status_code != 204:
            raise BabyBasicsAPIError(resp.status_code, resp.text)

    def _dispatch_action(self, action: str, params: dict) -> Any:
        if action == "baby_basics.log_feeding":
            return self.api_client.log_feeding(**params)
        elif action == "baby_basics.log_diaper":
            return self.api_client.log_diaper(**params)
        elif action == "baby_basics.toggle_sleep":
            return self.api_client.toggle_sleep(dashboard=self._sm.state.dashboard)
        elif action == "baby_basics.log_note":
            return self.api_client.log_note(**params)
        elif action.startswith("home_assistant."):
            return None
        else:
            raise ValueError(f"Unknown action: {action}")

    # --- Dashboard ---

    def _refresh_dashboard(self) -> None:
        try:
            dashboard = self.api_client.get_dashboard()
            self._sm.set_dashboard(dashboard, True, self.queue.count())
            if dashboard.active_sleep and not self._sm.state.sleep_active and self._sm.mode == "home_grid":
                self._sm.set_sleep_from_dashboard(dashboard.active_sleep.get("id"), dashboard.active_sleep.get("start_time"))
        except Exception:
            self._sm.set_connected(False)

    def _dashboard_poll_loop(self) -> None:
        interval = self.config.dashboard.poll_interval_seconds
        while not self._shutdown.is_set():
            self._shutdown.wait(interval)
            if not self._shutdown.is_set():
                self._refresh_dashboard()

    # --- Tick + Heartbeat ---

    def _display_tick_loop(self) -> None:
        while not self._shutdown.is_set():
            self._shutdown.wait(1)
            if self._shutdown.is_set():
                break
            tick = self._sm.advance_tick(time.monotonic())
            if tick.action == "confirmation_expired":
                self.refresh_display()
            elif tick.action == "detail_expired":
                self._commit_detail_default()
            elif tick.action == "refresh":
                self.refresh_display()
            elif tick.mode == "home_grid":
                self._check_brightness_schedule()

    def _check_brightness_schedule(self) -> None:
        schedule = self.config.display.brightness_schedule
        if not schedule.enabled:
            return
        now_time = datetime.now().time()
        if _in_time_range(now_time, _parse_time(schedule.night_start), _parse_time(schedule.night_end)):
            self._device.set_brightness(schedule.night_brightness)
        else:
            self._device.set_brightness(schedule.day_brightness)

    def _heartbeat_loop(self) -> None:
        while not self._shutdown.is_set():
            self._shutdown.wait(10)
            if not self._shutdown.is_set():
                self._device.send_heartbeat()

    # --- Sync callbacks ---

    def _on_sync_success(self, event: Any) -> None:
        self._sm.set_queued_count(self.queue.count())
        self._led.flash_sync_success()

    def _on_sync_failure(self, event: Any, error: str) -> None:
        self._sm.set_queued_count(self.queue.count())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    logger.info("Baby Basics Macropad v0.3.0")
    try:
        config = load_config()
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        sys.exit(1)

    controller = MacropadController(config)

    def _signal_handler(sig: int, frame: Any) -> None:
        controller.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    controller.start()
    controller.wait()
    controller.stop()


if __name__ == "__main__":
    main()
