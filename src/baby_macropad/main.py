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
from datetime import datetime, timezone
from datetime import time as dt_time
from typing import Any

from baby_macropad.actions.baby_basics import BabyBasicsClient, DashboardData
from baby_macropad.actions.dispatcher import DETAIL_CONFIGS, ActionDispatcher
from baby_macropad.actions.sleep_manager import SleepManager
from baby_macropad.actions.undo import UndoManager
from baby_macropad.config import SERVER_URLS, MacropadConfig, load_config
from baby_macropad.device import StreamDockDevice, StubDevice
from baby_macropad.offline.queue import OfflineQueue
from baby_macropad.offline.sync import SyncWorker
from baby_macropad.pairing.qr import generate_qr_image
from baby_macropad.pairing.server import (
    PairingServer,
    generate_pairing_code,
    get_local_ip,
    has_valid_pairing,
)
from baby_macropad.settings import SettingsModel
from baby_macropad.state import DisplayState
from baby_macropad.ui.framework.screen import ScreenRenderer
from baby_macropad.ui.key_router import KeyRouter
from baby_macropad.ui.led import LedController
from baby_macropad.ui.screens.confirmation import build_confirmation_screen
from baby_macropad.ui.screens.dashboard_screen import build_dashboard_screen
from baby_macropad.ui.screens.detail import build_detail_screen
from baby_macropad.ui.screens.home import build_home_grid
from baby_macropad.ui.screens.selection import build_selection_screen
from baby_macropad.ui.screens.settings_screen import build_settings_screen
from baby_macropad.ui.screens.setup_screen import (
    NAME_PRESETS,
    build_setup_name_screen,
    build_setup_qr_screen,
)
from baby_macropad.ui.screens.sleep_screen import build_sleep_screen
from baby_macropad.ui.state_machine import StateMachine

logger = logging.getLogger(__name__)

CONFIRMATION_DURATION = 5.0

_ICON_TO_DETAIL: dict[str, str] = {
    "breast_left": "breast_left", "breast_right": "breast_right",
    "bottle": "bottle", "diaper_pee": "pee", "diaper_poop": "poop", "diaper_both": "both",
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
        self._display_lock = threading.Lock()

        # State machine (thread-safe)
        self._sm = StateMachine(DisplayState(
            timer_seconds=config.settings_menu.timer_duration_seconds,
            skip_breast_detail=config.settings_menu.skip_breast_detail,
            celebration_style=config.settings_menu.celebration_style,
        ))

        # Settings model
        self._settings = SettingsModel.load()
        self._sm.sync_settings(
            self._settings.timer_duration_seconds,
            self._settings.celebration_style,
            self._settings.skip_breast_detail,
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
            queue=self.queue, get_api=lambda: self.api_client,
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
        self._led.quiet_hours_setting = self._settings.quiet_hours

        # Sub-controllers — use lambdas so queue/api replacement propagates correctly
        self._sleep_mgr = SleepManager(
            get_api=lambda: self.api_client, sm=self._sm, led=self._led,
            device=self._device, get_queue=lambda: self.queue, brightness=config.device.brightness,
            refresh_display=self.refresh_display, refresh_dashboard=self._refresh_dashboard,
        )
        self._dispatcher = ActionDispatcher(
            get_api=lambda: self.api_client, sm=self._sm, led=self._led,
            device=self._device, get_queue=lambda: self.queue, renderer=self._renderer,
            refresh_display=self.refresh_display, refresh_dashboard=self._refresh_dashboard,
        )
        self._undo_mgr = UndoManager(
            get_api=lambda: self.api_client, sm=self._sm, led=self._led,
            get_queue=lambda: self.queue, refresh_display=self.refresh_display,
            refresh_dashboard=self._refresh_dashboard,
        )

        # Pairing server (created on demand during setup flow)
        self._pairing_server: PairingServer | None = None
        self._qr_image = None

    def start(self) -> None:
        logger.info("Starting macropad controller")
        # Retry device discovery for up to 30s (USB may not be ready at boot)
        max_retries = 10
        for attempt in range(1, max_retries + 1):
            if self._device.open():
                break
            if attempt < max_retries:
                logger.info("Device not found, retrying (%d/%d)...", attempt, max_retries)
                time.sleep(3)
        else:
            logger.info("Using stub device (no hardware found after %d attempts)", max_retries)
            self._device = StubDevice()
            self._device.open()
            self._led = LedController(self._device)
            self._led.quiet_hours_setting = self._settings.quiet_hours

        self._device.set_brightness(self.config.device.brightness)

        # Auto-enter setup mode if no valid pairing exists
        if not has_valid_pairing(self._settings.server):
            logger.info("No valid pairing found — entering setup mode")
            self._sm.enter_setup_name()

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
        with self._display_lock:
            s = self._sm.state
            now = time.monotonic()

            if s.mode == "sleep_mode":
                elapsed, start_str = self._calc_sleep_elapsed()
                feed_count = None
                dashboard = s.dashboard
                if isinstance(dashboard, DashboardData) and dashboard.today_counts:
                    feed_count = dashboard.today_counts.get("feedings")
                screen = build_sleep_screen(elapsed, start_str, feed_count=feed_count)
            elif s.mode == "wake_confirm" and s.wake_confirm_from_sleep:
                # Reuse sleep data page with CONFIRM button (no timeout)
                elapsed, start_str = self._calc_sleep_elapsed()
                feed_count = None
                dashboard = s.dashboard
                if isinstance(dashboard, DashboardData) and dashboard.today_counts:
                    feed_count = dashboard.today_counts.get("feedings")
                screen = build_sleep_screen(elapsed, start_str, feed_count=feed_count, wake_pending=True)
            elif s.mode == "wake_confirm" and (s.wake_confirm_expires == 0 or now < s.wake_confirm_expires):
                elapsed, _ = self._calc_sleep_elapsed()
                if elapsed >= 60:
                    elapsed_text = f"{elapsed // 60}h {elapsed % 60}m"
                else:
                    elapsed_text = f"{elapsed}m"
                screen = build_detail_screen(
                    title="End Sleep?",
                    options=[{"label": "WAKE", "key_num": 8, "selected": True}],
                    timer_seconds=max(0, int(s.wake_confirm_expires - now)) if s.wake_confirm_expires > 0 else 0,
                    category_color=(102, 153, 204),
                    hint="Wake Up",
                    subtitle=elapsed_text,
                    icon="moon",
                )
            elif s.mode == "confirmation" and now < s.confirmation_expires:
                screen = build_confirmation_screen(
                    s.confirmation_label, s.confirmation_context,
                    s.confirmation_category_color,
                    resource_id=s.confirmation_resource_id,
                    icon=s.confirmation_icon,
                    layout=self._settings.confirmation_layout,
                    dashboard=s.dashboard,
                )
            elif s.mode == "detail" and (
                s.detail_timer_expires == 0.0 or now < s.detail_timer_expires
            ):
                cfg = DETAIL_CONFIGS.get(s.detail_action or "")
                selected_idx = s.detail_selected_index if s.detail_selected_index is not None else s.detail_default_index
                opts = [
                    {
                        "label": o["label"],
                        "key_num": o.get("key", 6 + i),
                        "selected": i == selected_idx,
                    }
                    for i, o in enumerate(s.detail_options)
                ]
                if s.detail_timer_expires > 0:
                    remaining = max(0, int(s.detail_timer_expires - now))
                else:
                    remaining = 0
                screen = build_detail_screen(
                    cfg["title"] if cfg else "DETAIL", opts,
                    remaining,
                    cfg["category_color"] if cfg else (200, 200, 200),
                    icon=cfg["confirmation_icon"] if cfg else "",
                    show_log_button=not self._settings.instant_log,
                )
            elif s.mode == "notes_submenu":
                cats = [
                    {"label": c.label, "icon": getattr(c, "icon", None)}
                    for c in self.config.notes_categories
                ]
                screen = build_selection_screen(cats, accent_color=(153, 153, 153))
            elif s.mode == "settings":
                screen = build_settings_screen(self._settings)
            elif s.mode == "setup_name":
                screen = build_setup_name_screen()
            elif s.mode == "setup_qr":
                status = "Paired!" if s.setup_paired else "Waiting..."
                qr_img = self._qr_image
                if qr_img is None:
                    # Fallback — generate a placeholder
                    from PIL import Image as PILImage
                    qr_img = PILImage.new("RGB", (50, 50), (0, 0, 0))
                screen = build_setup_qr_screen(
                    qr_image=qr_img,
                    name=s.setup_name,
                    code=s.setup_pairing_code,
                    status=status,
                )
            else:
                if s.mode != "home_grid":
                    self._sm.return_home()
                runtime_state = self._build_runtime_state()
                screen = build_home_grid(self.config.buttons, runtime_state)

            self._router.set_screen(screen)
            try:
                t_render = time.monotonic()
                jpeg = self._renderer.render(screen)
                t_encode = time.monotonic()
                self._device.set_screen_image(jpeg)
                t_send = time.monotonic()
                logger.info(
                    "Display refresh: mode=%s render=%.1fms send=%.1fms total=%.1fms (%d bytes)",
                    s.mode, (t_encode - t_render) * 1000,
                    (t_send - t_encode) * 1000,
                    (t_send - t_render) * 1000, len(jpeg),
                )
            except Exception:
                logger.exception("Failed to refresh display")

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

    @staticmethod
    def _remap_key(key: int) -> int:
        """Remap physical key codes — top/bottom rows are swapped on hardware.

        The StreamDock M18 sends keys 1-5 for the TOP physical row and
        keys 11-15 for the BOTTOM row, but the code and config use the
        opposite convention (11-15=top, 1-5=bottom). This swaps them so
        the visual layout matches the physical buttons.
        """
        if 1 <= key <= 5:
            return key + 10
        elif 11 <= key <= 15:
            return key - 10
        return key

    def _on_key_press(self, key: int, is_pressed: bool) -> None:
        t0 = time.monotonic()
        if not is_pressed:
            return

        key = self._remap_key(key)

        snap = self._sm.try_handle_key(key)
        if snap is None:
            return  # debounced
        t1 = time.monotonic()

        # Determine category for acknowledge flash color hint
        ack_category = "nav"
        if snap.mode == "home_grid":
            button = self.config.buttons.get(key)
            if button:
                icon = button.icon
                if icon in ("breast_left", "breast_right", "bottle"):
                    ack_category = "feeding"
                elif icon in ("diaper_pee", "diaper_poop", "diaper_both"):
                    ack_category = "diaper"
                elif icon == "sleep":
                    ack_category = "sleep_start"
                elif icon == "pump":
                    ack_category = "pump"
                elif icon == "note":
                    ack_category = "note"
        self._led.flash_acknowledge(ack_category)
        t2 = time.monotonic()

        logger.info(
            "Key %d pressed (mode=%s cat=%s) debounce=%.1fms led=%.1fms",
            key, snap.mode, ack_category, (t1 - t0) * 1000, (t2 - t1) * 1000,
        )

        if snap.mode == "home_grid":
            self._handle_home_grid_press(key)
        elif snap.mode == "detail":
            self._handle_detail_press(key)
        elif snap.mode == "confirmation":
            self._handle_confirmation_press(key, snap)
        elif snap.mode == "sleep_mode":
            self._handle_sleep_mode_press(key)
        elif snap.mode == "wake_confirm":
            self._handle_wake_confirm_press(key)
        elif snap.mode == "notes_submenu":
            self._handle_notes_submenu_press(key)
        elif snap.mode == "settings":
            self._handle_settings_press(key)
        elif snap.mode == "setup_name":
            self._handle_setup_name_press(key)
        elif snap.mode == "setup_qr":
            self._handle_setup_qr_press(key)

        logger.info("Key %d handler total=%.1fms", key, (time.monotonic() - t0) * 1000)

    def _handle_home_grid_press(self, key: int) -> None:
        button = self.config.buttons.get(key)
        if not button:
            return
        if button.action == "macropad.settings":
            self._sm.enter_settings()
            self.refresh_display()
        elif button.action == "baby_basics.notes_submenu":
            self._sm.enter_notes_submenu()
            self.refresh_display()
        elif button.action == "baby_basics.toggle_sleep":
            self._sleep_mgr.handle_sleep_toggle()
        elif (detail_key := _ICON_TO_DETAIL.get(button.icon)):
            if detail_key in ("breast_left", "breast_right") and self._sm.state.skip_breast_detail:
                self._dispatcher.execute_instant_action(button, key)
            else:
                self._dispatcher.enter_detail_screen(detail_key)
        else:
            self._dispatcher.execute_instant_action(button, key)

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
        # LOG button (key 5) — commit currently selected option
        if key == 5 and not self._settings.instant_log:
            selected = self._sm.state.detail_selected_index
            if selected is None:
                selected = cfg["default_index"]
            self._dispatcher.commit_detail_option(cfg, cfg["options"][selected])
            return
        for i, opt in enumerate(cfg["options"]):
            if key == opt["key"]:
                if self._settings.instant_log:
                    self._dispatcher.commit_detail_option(cfg, opt)
                else:
                    self._sm.select_detail_option(i)
                    self.refresh_display()
                return

    def _handle_confirmation_press(self, key: int, snap: Any) -> None:
        if key == 1 and snap.state.confirmation_resource_id:
            self._dispatcher.cancel_celebration()
            self._undo_mgr.execute_undo()
            return
        if key in (5, 15):
            self._dispatcher.cancel_celebration()
            self._sm.return_home()
            self.refresh_display()
            return
        # All other keys ignored during confirmation

    def _handle_sleep_mode_press(self, key: int) -> None:
        self._device.set_brightness(self.config.device.brightness)
        if key == 5:
            self._sleep_mgr.enter_wake_confirm(from_sleep=True)
        elif key == 1:
            self._device.set_brightness(10)  # Re-dim (CANCEL)
        elif key == 15:
            self._sm.return_home()
            self.refresh_display()
        else:
            self.refresh_display()

    def _handle_wake_confirm_press(self, key: int) -> None:
        if self._sm.state.wake_confirm_from_sleep:
            # Sleep data page with CONFIRM/CANCEL buttons
            if key == 5:
                self._sleep_mgr.handle_wake_up()
                return
            if key == 1:
                self._sm.resume_sleep_mode()
                self._device.set_brightness(10)
                self.refresh_display()
                return
            if key == 15:
                self._sm.return_home()
                self.refresh_display()
                return
            # Other keys: just refresh (keep screen awake)
            self.refresh_display()
            return
        if key == 1:
            self._sm.return_home()
            self.refresh_display()
            return
        if key == 8:
            # Confirm → end sleep
            self._sleep_mgr.handle_wake_up()
            return

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
                self._dispatcher.execute_note_action(
                    cat.content or cat.label, cat.label, getattr(cat, "api_category", "other")
                )
                return

    def _handle_settings_press(self, key: int) -> None:
        if key == 1:
            self._sm.return_home()
            self.refresh_display()
            return
        # Settings cards at keys 6-10 (row 1) and 2-5 (row 2); row 0 is header
        setting_keys = [6, 7, 8, 9, 10, 2, 3, 4, 5]
        visible_fields = [n for n, f in type(self._settings).model_fields.items()
                          if not (f.json_schema_extra or {}).get("hidden")]
        for i, field_name in enumerate(visible_fields):
            if i < len(setting_keys) and key == setting_keys[i]:
                self._settings.cycle_field(field_name)
                # Sync timer_seconds and other settings to state
                self._sm.sync_settings(
                    self._settings.timer_duration_seconds,
                    self._settings.celebration_style,
                    self._settings.skip_breast_detail,
                )
                # Apply brightness immediately if that's what changed
                self._device.set_brightness(self._settings.brightness)
                # Sync quiet hours to LED controller
                self._led.quiet_hours_setting = self._settings.quiet_hours
                # Recreate API client when server changes
                if field_name == "server":
                    self._rebuild_api_client()
                self.refresh_display()
                return

    def _handle_setup_name_press(self, key: int) -> None:
        if key == 1:
            self._sm.return_home()
            self.refresh_display()
            return
        option_keys = [11, 12, 13, 14, 15, 6, 7, 8, 9, 10, 2, 3, 4, 5]
        for i, name in enumerate(NAME_PRESETS):
            if i >= len(option_keys):
                break
            if key == option_keys[i]:
                self._start_pairing(name)
                return

    def _handle_setup_qr_press(self, key: int) -> None:
        if key == 1:
            # BACK — stop pairing server, return to name selection
            if self._pairing_server:
                self._pairing_server.stop()
                self._pairing_server = None
            self._sm.enter_setup_name()
            self.refresh_display()
            return

    def _start_pairing(self, name: str) -> None:
        """Start the pairing server and transition to the QR screen."""
        code = generate_pairing_code()
        ip = get_local_ip()
        port = 31337

        self._pairing_server = PairingServer(
            code=code,
            name=name,
            on_paired=self._on_pairing_complete,
            port=port,
        )
        self._pairing_server.start()
        actual_port = self._pairing_server.port

        # Generate QR payload: IP:PORT:CODE:NAME
        qr_data = f"{ip}:{actual_port}:{code}:{name}"
        self._qr_image = generate_qr_image(qr_data)

        self._sm.enter_setup_qr(name, code)
        self.refresh_display()
        logger.info("Pairing started: %s (QR payload: %s)", name, qr_data)

    def _on_pairing_complete(self, config: dict) -> None:
        """Called from pairing server thread when pairing succeeds."""
        logger.info("Pairing complete! Config: %s", config)
        self._sm.mark_setup_paired()
        self.refresh_display()

        # After 2s, rebuild API client and return home
        def _finalize() -> None:
            time.sleep(2)
            self._rebuild_api_client_from_pairing(config)
            self._sm.return_home()
            self.refresh_display()
            threading.Thread(target=self._refresh_dashboard, daemon=True).start()

        threading.Thread(target=_finalize, daemon=True, name="pairing-finalize").start()

    def _rebuild_api_client_from_pairing(self, config: dict) -> None:
        """Rebuild API client using pairing config for the current server."""
        server = self._settings.server
        server_config = config.get(server, {})
        api_url = server_config.get("api_url", SERVER_URLS.get(server, SERVER_URLS["dev"]))
        token = server_config.get("token", "")
        child_id = server_config.get("child_id", "")

        if not token:
            logger.warning("No token in pairing config for server %s", server)
            return

        logger.info("Rebuilding API client from pairing: server=%s url=%s", server, api_url)
        self.api_client.close()
        self.api_client = BabyBasicsClient(
            api_url=api_url,
            token=token,
            child_id=child_id,
        )

    def _rebuild_api_client(self) -> None:
        """Close old API client and create a new one for the selected server."""
        new_url = SERVER_URLS.get(self._settings.server, SERVER_URLS["dev"])
        logger.info("Switching API server to %s (%s)", self._settings.server, new_url)
        self.api_client.close()
        self.api_client = BabyBasicsClient(
            api_url=new_url,
            token=self.config.baby_basics.token,
            child_id=self.config.baby_basics.child_id,
        )

    # --- Thin delegators for backwards compatibility ---

    def _handle_sleep_toggle(self) -> None:
        self._sleep_mgr.handle_sleep_toggle()

    def _enter_wake_confirm(self, from_sleep: bool = False) -> None:
        self._sleep_mgr.enter_wake_confirm(from_sleep=from_sleep)

    def _handle_wake_up(self) -> None:
        self._sleep_mgr.handle_wake_up()

    def _commit_detail_default(self) -> None:
        self._dispatcher.commit_detail_default()

    def _dispatch_action(self, action: str, params: dict) -> Any:
        return self._dispatcher.dispatch_action(action, params)

    def _execute_undo(self) -> None:
        self._undo_mgr.execute_undo()

    # --- Dashboard ---

    def _refresh_dashboard(self) -> None:
        try:
            dashboard = self.api_client.get_dashboard()
            self._sm.set_dashboard(dashboard, True, self.queue.count())
            self._sm.mark_home_dirty()
            if dashboard.active_sleep and not self._sm.state.sleep_active and self._sm.mode == "home_grid":
                sleep_id = dashboard.active_sleep.get("id")
                # Don't re-activate a sleep we just ended (API may lag behind)
                if sleep_id and sleep_id == self._sm.state.ended_sleep_id:
                    logger.debug("Ignoring ended sleep %s still in dashboard", sleep_id[:8])
                else:
                    self._sm.set_sleep_from_dashboard(sleep_id, dashboard.active_sleep.get("start_time"))
            # Clear ended_sleep_id once dashboard confirms it's gone
            if not dashboard.active_sleep and self._sm.state.ended_sleep_id:
                self._sm.clear_ended_sleep()
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
                self._dispatcher.commit_detail_default()
            elif tick.action == "wake_confirm_expired":
                self._sleep_mgr.handle_wake_up()
            elif tick.action == "refresh":
                if tick.mode == "home_grid":
                    self._sm.clear_home_dirty()
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    from importlib.metadata import version as pkg_version
    try:
        _version = pkg_version("baby-macropad")
    except Exception:
        _version = "dev"
    logger.info("Baby Basics Macropad v%s", _version)
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
