"""Background sync worker that replays queued events to the API."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

from baby_macropad.offline.queue import OfflineQueue, QueuedEvent

if TYPE_CHECKING:
    from baby_macropad.actions.baby_basics import BabyBasicsClient

logger = logging.getLogger(__name__)

# Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, 60s cap
MIN_BACKOFF = 1.0
MAX_BACKOFF = 60.0
MAX_ATTEMPTS = 5


class SyncWorker:
    """Background thread that flushes the offline queue when the API is reachable."""

    def __init__(
        self,
        queue: OfflineQueue,
        api_client: BabyBasicsClient,
        on_sync_success: Callable[[QueuedEvent], None] | None = None,
        on_sync_failure: Callable[[QueuedEvent, str], None] | None = None,
        poll_interval: float = 10.0,
    ):
        self.queue = queue
        self.api_client = api_client
        self.on_sync_success = on_sync_success
        self.on_sync_failure = on_sync_failure
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background sync thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sync-worker")
        self._thread.start()
        logger.info("Sync worker started")

    def stop(self) -> None:
        """Signal the sync thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            logger.info("Sync worker stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._flush()
            except Exception:
                logger.exception("Sync worker error during flush")
            self._stop_event.wait(self.poll_interval)

    def _flush(self) -> None:
        """Try to send all queued events, oldest first."""
        events = self.queue.peek(limit=20)
        if not events:
            return

        logger.info("Flushing %d queued events", len(events))
        for event in events:
            if self._stop_event.is_set():
                break
            if event.attempts >= MAX_ATTEMPTS:
                logger.warning("Event %s exceeded max attempts, dropping", event.id[:8])
                self.queue.mark_done(event.id)
                if self.on_sync_failure:
                    self.on_sync_failure(event, "max_attempts_exceeded")
                continue
            try:
                self._dispatch(event)
                self.queue.mark_done(event.id)
                if self.on_sync_success:
                    self.on_sync_success(event)
            except Exception as e:
                error_msg = str(e)
                logger.warning("Failed to sync event %s: %s", event.id[:8], error_msg)
                self.queue.mark_failed(event.id, error_msg)
                if self.on_sync_failure:
                    self.on_sync_failure(event, error_msg)
                # Back off on first failure — don't hammer the API
                break

    def _dispatch(self, event: QueuedEvent) -> None:
        """Route a queued event to the appropriate API method."""
        action = event.action
        params = event.params

        if action == "baby_basics.log_feeding":
            self.api_client.log_feeding(**params)
        elif action == "baby_basics.log_diaper":
            self.api_client.log_diaper(**params)
        elif action == "baby_basics.toggle_sleep":
            self.api_client.toggle_sleep()
        elif action == "baby_basics.log_note":
            self.api_client.log_note(**params)
        else:
            logger.error("Unknown action in queue: %s", action)
            raise ValueError(f"Unknown action: {action}")

    def flush_now(self) -> int:
        """Synchronously flush the queue. Returns number of events synced."""
        synced = 0
        events = self.queue.peek(limit=50)
        for event in events:
            if event.attempts >= MAX_ATTEMPTS:
                self.queue.mark_done(event.id)
                if self.on_sync_failure:
                    self.on_sync_failure(event, "max_attempts_exceeded")
                continue
            try:
                self._dispatch(event)
                self.queue.mark_done(event.id)
                synced += 1
                if self.on_sync_success:
                    self.on_sync_success(event)
            except Exception as e:
                error_msg = str(e)
                self.queue.mark_failed(event.id, error_msg)
                if self.on_sync_failure:
                    self.on_sync_failure(event, error_msg)
                break
        return synced
