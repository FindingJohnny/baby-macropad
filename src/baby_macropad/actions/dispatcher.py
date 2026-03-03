"""Action dispatching: detail screens, API calls, confirmations, celebrations."""
from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from baby_macropad.actions.baby_basics import BabyBasicsAPIError, DashboardData

if TYPE_CHECKING:
    from baby_macropad.actions.baby_basics import BabyBasicsClient
    from baby_macropad.device import DeviceProtocol
    from baby_macropad.ui.framework.screen import ScreenRenderer
    from baby_macropad.ui.led import LedController
    from baby_macropad.ui.state_machine import StateMachine

logger = logging.getLogger(__name__)

CONFIRMATION_DURATION = 5.0

# Detail screen configurations (maps action key → options, API action, params)
DETAIL_CONFIGS: dict[str, dict[str, Any]] = {
    "breast_left": {
        "title": "LEFT",
        "options": [
            {"label": "One", "key": 12, "value": {"both_sides": False}},
            {"label": "Both", "key": 13, "value": {"both_sides": True}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102), "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "breast", "started_side": "left"},
        "confirmation_label": "Fed L", "confirmation_icon": "breast_left",
        "resource_type": "feedings", "column": 0,
    },
    "breast_right": {
        "title": "RIGHT",
        "options": [
            {"label": "One", "key": 12, "value": {"both_sides": False}},
            {"label": "Both", "key": 13, "value": {"both_sides": True}},
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
            {"label": "Formula", "key": 12, "value": {"source": "formula"}},
            {"label": "Brst Milk", "key": 13, "value": {"source": "breast_milk"}},
            {"label": "Skip", "key": 14, "value": {}},
        ],
        "default_index": 0,
        "category_color": (102, 204, 102), "category": "feeding",
        "api_action": "baby_basics.log_feeding",
        "base_params": {"type": "bottle"},
        "confirmation_label": "Bottle", "confirmation_icon": "bottle",
        "resource_type": "feedings", "column": 0,
    },
    "pee": {
        "title": "PEE",
        "options": [
            {"label": "Log", "key": 13, "value": {}},
        ],
        "default_index": 0,
        "category_color": (204, 170, 68), "category": "diaper",
        "api_action": "baby_basics.log_diaper",
        "base_params": {"type": "pee"},
        "confirmation_label": "Pee", "confirmation_icon": "diaper_pee",
        "resource_type": "diapers", "column": 1,
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
        "confirmation_label": "Pee +\nPoop", "confirmation_icon": "diaper_both",
        "resource_type": "diapers", "column": 1,
    },
}

_ICON_TO_DETAIL: dict[str, str] = {
    "breast_left": "breast_left", "breast_right": "breast_right",
    "bottle": "bottle", "diaper_pee": "pee", "diaper_poop": "poop", "diaper_both": "both",
}
_KEY_TO_COLUMN: dict[int, int] = {
    11: 0, 6: 0, 1: 0, 12: 1, 7: 1, 2: 1, 13: 2, 8: 2, 3: 2,
    14: 3, 9: 3, 4: 3, 15: 4, 10: 4, 5: 4,
}


class ActionDispatcher:
    def __init__(
        self,
        api_client: BabyBasicsClient,
        sm: StateMachine,
        led: LedController,
        device: DeviceProtocol,
        get_queue: Any,  # callable returning OfflineQueue
        renderer: ScreenRenderer,
        refresh_display: Any,
        refresh_dashboard: Any,
    ) -> None:
        self._api = api_client
        self._sm = sm
        self._led = led
        self._device = device
        self._get_queue = get_queue
        self._renderer = renderer
        self._refresh_display = refresh_display
        self._refresh_dashboard = refresh_dashboard

    def enter_detail_screen(self, detail_key: str) -> None:
        cfg = DETAIL_CONFIGS.get(detail_key)
        if not cfg:
            return
        timer = self._sm.state.timer_seconds
        expires = time.monotonic() + timer if timer > 0 else 0.0
        self._sm.enter_detail(
            detail_key, cfg["options"], cfg["default_index"], dict(cfg["base_params"]), expires
        )
        self._refresh_display()

    def commit_detail_option(self, cfg: dict, option: dict) -> None:
        params = dict(cfg["base_params"])
        params.update(option.get("value", {}))
        self.call_api_and_confirm(
            cfg["api_action"], params, cfg["confirmation_label"], cfg["confirmation_icon"],
            cfg["category_color"], cfg["category"], cfg["column"], cfg["resource_type"],
        )

    def commit_detail_default(self) -> None:
        if self._sm.mode != "detail":
            return
        cfg = DETAIL_CONFIGS.get(self._sm.get_detail_action() or "")
        if not cfg:
            self._sm.return_home()
            self._refresh_display()
            return
        self.commit_detail_option(cfg, cfg["options"][cfg["default_index"]])

    def execute_instant_action(self, button: Any, key: int) -> None:
        icon_name = button.icon
        column = _KEY_TO_COLUMN.get(key, 0)
        if icon_name == "diaper_pee":
            cat, label, rtype = "diaper", "Pee", "diapers"
        elif icon_name == "pump":
            cat, label, rtype = "pump", "Pump", "notes"
        else:
            cat, label, rtype = "feeding", button.label, "feedings"
        color = {"feeding": (102, 204, 102), "diaper": (204, 170, 68)}.get(cat, (200, 200, 200))
        self.call_api_and_confirm(
            button.action, dict(button.params), label, icon_name, color, cat, column, rtype
        )

    def execute_note_action(self, content: str, label: str, category: str = "other") -> None:
        self.call_api_and_confirm(
            "baby_basics.log_note",
            {"category": category, "title": label, "text": content},
            label, "note", (153, 153, 153), "note", 2, "notes",
        )

    def call_api_and_confirm(
        self, api_action: str, params: dict, label: str, icon: str,
        category_color: tuple[int, int, int], category: str, column: int, resource_type: str,
    ) -> None:
        resource_id = None
        context_line = ""
        try:
            result = self.dispatch_action(api_action, params)
            if isinstance(result, dict):
                for k in (resource_type[:-1], resource_type):
                    if k in result and isinstance(result[k], dict):
                        resource_id = result[k].get("id")
                        break
                if not resource_id:
                    resource_id = result.get("id")
            action_name = api_action.removeprefix("baby_basics.")
            self._sm.apply_optimistic_update(action_name, params)
            context_line = self._build_context_line(category)
            self._led.flash_category(category)
        except (
            BabyBasicsAPIError, ConnectionError, httpx.TimeoutException, httpx.ConnectError
        ) as e:
            logger.warning("Action failed, queueing offline: %s", e)
            self._get_queue().enqueue(api_action, params)
            context_line = "Queued"
            self._led.flash_queued()

        if resource_id:
            self._sm.push_recent_action({
                "resource_id": resource_id, "resource_type": resource_type,
                "label": label, "timestamp": datetime.now(UTC).isoformat(),
            })
        self._sm.enter_confirmation(
            api_action, label, context_line, icon, category_color, column,
            time.monotonic() + CONFIRMATION_DURATION, resource_id, resource_type,
        )
        self._play_celebration(category_color, self._sm.state.celebration_style)
        self._refresh_display()
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _play_celebration(self, category_color: tuple[int, int, int],
                          style: str) -> None:
        """Play celebration animation before showing confirmation screen."""
        if style == "none":
            return
        frames = self._build_celebration_frames(category_color, style)
        for i, frame_jpeg in enumerate(frames):
            try:
                self._device.set_screen_image(frame_jpeg)
                time.sleep(0.08)
            except Exception:
                logger.exception("Celebration frame %d failed", i)
                break

    def _build_celebration_frames(
        self, category_color: tuple[int, int, int], style: str,
    ) -> list[bytes]:
        """Pre-render celebration frames as JPEG bytes.

        - flash: 1 frame — full screen category color + checkmark
        - pulse: 2 frames — full color, then top row only
        - ripple: 3 frames — center col, center+adjacent, all cols (top row)
        """
        from baby_macropad.ui.framework.screen import CellDef, ScreenDef
        from baby_macropad.ui.framework.widgets import Card, Icon, Spacer

        def _color_cells(keys: set[int]) -> dict[int, CellDef]:
            cells: dict[int, CellDef] = {}
            for key in keys:
                cells[key] = CellDef(
                    widget=Card(fill=category_color, child=Spacer()),
                    key_num=key,
                )
            return cells

        top_row = {11, 12, 13, 14, 15}
        all_keys = set(range(1, 16))

        if style == "flash":
            cells = _color_cells(all_keys)
            cells[8] = CellDef(
                widget=Card(
                    fill=category_color,
                    child=Icon(asset_name="check", color=(255, 255, 255), size=36),
                ),
                key_num=8,
            )
            return [self._renderer.render(ScreenDef(name="celebration", cells=cells))]

        elif style == "pulse":
            cells1 = _color_cells(all_keys)
            cells1[8] = CellDef(
                widget=Card(
                    fill=category_color,
                    child=Icon(asset_name="check", color=(255, 255, 255), size=36),
                ),
                key_num=8,
            )
            cells2 = _color_cells(top_row)
            return [
                self._renderer.render(ScreenDef(name="celebration", cells=cells1)),
                self._renderer.render(ScreenDef(name="celebration", cells=cells2)),
            ]

        elif style == "ripple":
            cells1 = _color_cells({13})
            cells2 = _color_cells({12, 13, 14})
            cells3 = _color_cells(top_row)
            return [
                self._renderer.render(ScreenDef(name="celebration", cells=cells1)),
                self._renderer.render(ScreenDef(name="celebration", cells=cells2)),
                self._renderer.render(ScreenDef(name="celebration", cells=cells3)),
            ]

        return []

    def _build_context_line(self, category: str) -> str:
        dashboard = self._sm.state.dashboard
        if not isinstance(dashboard, DashboardData):
            return ""
        counts = dashboard.today_counts
        if category == "feeding":
            side = dashboard.suggested_side
            return f"Next: {side[0].upper()}" if side else f"{counts.get('feedings', 0)} feeds"
        elif category == "diaper":
            return f"{counts.get('diapers', 0)} diapers"
        elif category == "pump":
            return "Pumped"
        return ""

    def dispatch_action(self, action: str, params: dict) -> Any:
        if action == "baby_basics.log_feeding":
            return self._api.log_feeding(**params)
        elif action == "baby_basics.log_diaper":
            return self._api.log_diaper(**params)
        elif action == "baby_basics.toggle_sleep":
            return self._api.toggle_sleep(dashboard=self._sm.state.dashboard)
        elif action == "baby_basics.log_note":
            return self._api.log_note(**params)
        elif action.startswith("home_assistant."):
            return None
        else:
            raise ValueError(f"Unknown action: {action}")
