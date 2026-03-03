"""Undo manager: delete recently logged resources."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import httpx

from baby_macropad.actions.baby_basics import BabyBasicsAPIError

if TYPE_CHECKING:
    from baby_macropad.actions.baby_basics import BabyBasicsClient
    from baby_macropad.ui.led import LedController
    from baby_macropad.ui.state_machine import StateMachine

logger = logging.getLogger(__name__)


class UndoManager:
    def __init__(
        self,
        api_client: BabyBasicsClient,
        sm: StateMachine,
        led: LedController,
        get_queue: Any,  # callable returning OfflineQueue
        refresh_display: Any,
        refresh_dashboard: Any,
    ) -> None:
        self._api = api_client
        self._sm = sm
        self._led = led
        self._get_queue = get_queue
        self._refresh_display = refresh_display
        self._refresh_dashboard = refresh_dashboard

    def execute_undo(self) -> None:
        rid = self._sm.get_confirmation_resource_id()
        rtype = self._sm.get_confirmation_resource_type()
        if not rid or not rtype:
            self._sm.return_home()
            self._refresh_display()
            return
        try:
            self._delete_resource(rtype, rid)
            self._led.flash_undo()
        except (
            BabyBasicsAPIError, ConnectionError, httpx.TimeoutException, httpx.ConnectError
        ) as e:
            logger.warning("Undo failed, queueing: %s", e)
            self._get_queue().enqueue(f"baby_basics.delete_{rtype}", {"resource_id": rid})
            self._led.flash_queued()
        self._sm.remove_recent_action(rid)
        self._sm.return_home()
        self._refresh_display()
        threading.Thread(target=self._refresh_dashboard, daemon=True).start()

    def _delete_resource(self, resource_type: str, resource_id: str) -> None:
        self._api.delete_resource(resource_type, resource_id)
