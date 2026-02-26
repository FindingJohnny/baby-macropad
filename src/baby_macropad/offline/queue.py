"""SQLite offline event queue for resilient event buffering."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".baby-macropad" / "queue.db"
MAX_QUEUE_SIZE = 1000


@dataclass
class QueuedEvent:
    """A single queued event waiting to be synced."""

    id: str
    action: str
    params: dict[str, Any]
    created_at: str
    attempts: int = 0
    last_error: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> QueuedEvent:
        return cls(
            id=row["id"],
            action=row["action"],
            params=json.loads(row["params"]),
            created_at=row["created_at"],
            attempts=row["attempts"],
            last_error=row["last_error"],
        )


class OfflineQueue:
    """SQLite-backed queue for offline event buffering.

    Events are stored when the API is unreachable and replayed
    when connectivity is restored. Each event has a client-generated
    UUID for idempotency.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS event_queue (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                params TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                last_error TEXT
            )
        """)
        self._conn.commit()

    def enqueue(self, action: str, params: dict[str, Any]) -> str:
        """Add an event to the offline queue. Returns the event ID."""
        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        # Enforce max queue size — drop oldest if full
        count = self._conn.execute("SELECT COUNT(*) FROM event_queue").fetchone()[0]
        if count >= MAX_QUEUE_SIZE:
            self._conn.execute("""
                DELETE FROM event_queue WHERE id IN (
                    SELECT id FROM event_queue ORDER BY created_at ASC LIMIT 1
                )
            """)

        self._conn.execute(
            "INSERT INTO event_queue (id, action, params, created_at) VALUES (?, ?, ?, ?)",
            (event_id, action, json.dumps(params), created_at),
        )
        self._conn.commit()
        logger.info("Queued event %s: %s", event_id[:8], action)
        return event_id

    def peek(self, limit: int = 10) -> list[QueuedEvent]:
        """Get the oldest events without removing them."""
        rows = self._conn.execute(
            "SELECT * FROM event_queue ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [QueuedEvent.from_row(r) for r in rows]

    def mark_done(self, event_id: str) -> None:
        """Remove a successfully synced event from the queue."""
        self._conn.execute("DELETE FROM event_queue WHERE id = ?", (event_id,))
        self._conn.commit()
        logger.info("Dequeued event %s", event_id[:8])

    def mark_failed(self, event_id: str, error: str) -> None:
        """Increment attempt count and record the error."""
        self._conn.execute(
            "UPDATE event_queue SET attempts = attempts + 1, last_error = ? WHERE id = ?",
            (error, event_id),
        )
        self._conn.commit()

    def count(self) -> int:
        """Number of events in the queue."""
        return self._conn.execute("SELECT COUNT(*) FROM event_queue").fetchone()[0]

    def clear(self) -> None:
        """Remove all events (for testing or manual reset)."""
        self._conn.execute("DELETE FROM event_queue")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
