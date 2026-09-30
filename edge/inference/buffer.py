"""
Durable outbox for telemetry the edge agent couldn't publish because the
cloud MQTT broker was unreachable. Backed by SQLite (not an in-memory
list) so a buffered reading survives an edge-device power cycle, not
just a brief network blip — the scenario this phase is meant to harden
against is exactly the kind of event that also tends to kill process
memory.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Tuple


class DurableBuffer:
    """
    paho-mqtt's `loop_start()` runs its network I/O (and therefore the
    `on_connect` callback that triggers a flush) on its own background
    thread, while the agent's main loop calls `push()` concurrently from
    the main thread — so this is genuinely accessed from more than one
    thread, not just constructed in one and used in another. sqlite3
    connections are single-thread by default (`check_same_thread=True`
    raises exactly this case); opting out of that check is only safe
    paired with a lock that serializes every actual statement.
    """

    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                buffered_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def push(self, topic: str, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO outbox (topic, payload, buffered_at) VALUES (?, ?, ?)",
                (topic, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
            )
            self._conn.commit()

    def pending(self) -> List[Tuple[int, str, dict]]:
        """All buffered items, oldest first — the order they must be republished in."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, topic, payload FROM outbox ORDER BY id ASC"
            ).fetchall()
        return [(row_id, topic, json.loads(payload)) for row_id, topic, payload in rows]

    def ack(self, row_id: int) -> None:
        """Remove one buffered item once its republish is confirmed delivered."""
        with self._lock:
            self._conn.execute("DELETE FROM outbox WHERE id = ?", (row_id,))
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
