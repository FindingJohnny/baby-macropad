"""Tests for offline SQLite queue and sync worker."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baby_macropad.offline.queue import OfflineQueue, QueuedEvent
from baby_macropad.offline.sync import SyncWorker


@pytest.fixture
def queue(tmp_path: Path) -> OfflineQueue:
    q = OfflineQueue(db_path=tmp_path / "test_queue.db")
    yield q
    q.close()


class TestOfflineQueue:
    def test_enqueue_and_peek(self, queue: OfflineQueue):
        event_id = queue.enqueue("baby_basics.log_feeding", {"type": "breast", "started_side": "left"})
        assert event_id  # UUID string
        events = queue.peek()
        assert len(events) == 1
        assert events[0].action == "baby_basics.log_feeding"
        assert events[0].params == {"type": "breast", "started_side": "left"}
        assert events[0].attempts == 0

    def test_mark_done_removes_event(self, queue: OfflineQueue):
        event_id = queue.enqueue("baby_basics.log_diaper", {"type": "pee"})
        assert queue.count() == 1
        queue.mark_done(event_id)
        assert queue.count() == 0

    def test_mark_failed_increments_attempts(self, queue: OfflineQueue):
        event_id = queue.enqueue("baby_basics.log_note", {"content": "test"})
        queue.mark_failed(event_id, "Connection refused")
        events = queue.peek()
        assert events[0].attempts == 1
        assert events[0].last_error == "Connection refused"

    def test_fifo_ordering(self, queue: OfflineQueue):
        queue.enqueue("baby_basics.log_feeding", {"type": "breast"})
        queue.enqueue("baby_basics.log_diaper", {"type": "poop"})
        queue.enqueue("baby_basics.log_note", {"content": "test"})
        events = queue.peek(limit=3)
        assert [e.action for e in events] == [
            "baby_basics.log_feeding",
            "baby_basics.log_diaper",
            "baby_basics.log_note",
        ]

    def test_max_queue_size_drops_oldest(self, queue: OfflineQueue):
        # Fill to max
        for i in range(1000):
            queue.enqueue("baby_basics.log_note", {"content": f"note-{i}"})
        assert queue.count() == 1000

        # Adding one more should drop the oldest
        queue.enqueue("baby_basics.log_note", {"content": "overflow"})
        assert queue.count() == 1000
        events = queue.peek(limit=1)
        # The oldest (note-0) should have been dropped; now note-1 is oldest
        assert events[0].params["content"] == "note-1"

    def test_clear(self, queue: OfflineQueue):
        queue.enqueue("baby_basics.log_feeding", {"type": "bottle"})
        queue.enqueue("baby_basics.log_diaper", {"type": "pee"})
        assert queue.count() == 2
        queue.clear()
        assert queue.count() == 0

    def test_count_empty(self, queue: OfflineQueue):
        assert queue.count() == 0

    def test_peek_with_limit(self, queue: OfflineQueue):
        for i in range(5):
            queue.enqueue("baby_basics.log_note", {"content": f"note-{i}"})
        events = queue.peek(limit=2)
        assert len(events) == 2


class TestSyncWorker:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.log_feeding = MagicMock(return_value={"feeding": {"id": "f1"}})
        client.log_diaper = MagicMock(return_value={"diaper": {"id": "d1"}})
        client.log_note = MagicMock(return_value={"note": {"id": "n1"}})
        client.toggle_sleep = MagicMock(return_value={"sleep": {"id": "s1"}})
        return client

    def test_flush_now_syncs_events(self, queue: OfflineQueue, mock_client: MagicMock):
        queue.enqueue("baby_basics.log_feeding", {"type": "breast", "started_side": "left"})
        queue.enqueue("baby_basics.log_diaper", {"type": "pee"})

        worker = SyncWorker(queue=queue, api_client=mock_client)
        synced = worker.flush_now()

        assert synced == 2
        assert queue.count() == 0
        mock_client.log_feeding.assert_called_once_with(type="breast", started_side="left")
        mock_client.log_diaper.assert_called_once_with(type="pee")

    def test_flush_now_stops_on_failure(self, queue: OfflineQueue, mock_client: MagicMock):
        queue.enqueue("baby_basics.log_feeding", {"type": "breast"})
        queue.enqueue("baby_basics.log_diaper", {"type": "pee"})
        mock_client.log_feeding.side_effect = ConnectionError("No network")

        worker = SyncWorker(queue=queue, api_client=mock_client)
        synced = worker.flush_now()

        assert synced == 0
        assert queue.count() == 2
        # First event should have 1 attempt now
        events = queue.peek()
        assert events[0].attempts == 1

    def test_flush_now_drops_after_max_attempts(self, queue: OfflineQueue, mock_client: MagicMock):
        event_id = queue.enqueue("baby_basics.log_feeding", {"type": "breast"})
        # Manually set attempts to max
        for _ in range(5):
            queue.mark_failed(event_id, "error")

        worker = SyncWorker(queue=queue, api_client=mock_client)
        synced = worker.flush_now()

        assert synced == 0
        assert queue.count() == 0  # Dropped
        mock_client.log_feeding.assert_not_called()

    def test_dispatch_toggle_sleep(self, queue: OfflineQueue, mock_client: MagicMock):
        queue.enqueue("baby_basics.toggle_sleep", {})
        worker = SyncWorker(queue=queue, api_client=mock_client)
        synced = worker.flush_now()
        assert synced == 1
        mock_client.toggle_sleep.assert_called_once()

    def test_dispatch_log_note(self, queue: OfflineQueue, mock_client: MagicMock):
        queue.enqueue("baby_basics.log_note", {"content": "Quick note"})
        worker = SyncWorker(queue=queue, api_client=mock_client)
        synced = worker.flush_now()
        assert synced == 1
        mock_client.log_note.assert_called_once_with(content="Quick note")

    def test_callbacks_called(self, queue: OfflineQueue, mock_client: MagicMock):
        on_success = MagicMock()
        on_failure = MagicMock()
        queue.enqueue("baby_basics.log_feeding", {"type": "breast"})

        worker = SyncWorker(
            queue=queue,
            api_client=mock_client,
            on_sync_success=on_success,
            on_sync_failure=on_failure,
        )
        worker.flush_now()

        on_success.assert_called_once()
        on_failure.assert_not_called()
