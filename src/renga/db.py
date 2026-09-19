"""The append-only event log, the single source of truth the room is a view
of. Carried over from agentville. One SQLite file for now; a hosted store
replaces it when the agents move onto modal."""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("RENGA_DB", Path(__file__).resolve().parents[2] / "renga.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    channel TEXT NOT NULL,
    from_agent TEXT NOT NULL,
    to_agent TEXT,
    kind TEXT NOT NULL,
    text TEXT,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_channel ON events(channel);
"""


def _row_to_event(row: tuple) -> dict[str, Any]:
    id_, ts, channel, from_agent, to_agent, kind, text, data = row
    event: dict[str, Any] = {"id": id_, "ts": ts, "channel": channel, "from": from_agent, "kind": kind}
    if to_agent is not None:
        event["to"] = to_agent
    if text is not None:
        event["text"] = text
    if data is not None:
        event["data"] = json.loads(data)
    return event


class EventStore:
    """Thread-safe wrapper around the one SQLite file. Sync on purpose:
    FastAPI runs sync calls in a worker thread, and the log never needs to
    hold a connection open across an await."""

    def __init__(self, path: Path = DB_PATH):
        self._path = path
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, check_same_thread=False)

    def append(
        self,
        channel: str,
        kind: str,
        from_: str = "admin",
        to: str | None = None,
        text: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ts = int(time.time() * 1000)
        data_json = json.dumps(data) if data is not None else None
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO events (ts, channel, from_agent, to_agent, kind, text, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, channel, from_, to, kind, text, data_json),
            )
            event_id = cur.lastrowid
        return _row_to_event((event_id, ts, channel, from_, to, kind, text, data_json))

    def since(self, since_id: int = 0, channel: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT id, ts, channel, from_agent, to_agent, kind, text, data FROM events WHERE id > ?"
        params: list[Any] = [since_id]
        if channel:
            query += " AND channel = ?"
            params.append(channel)
        query += " ORDER BY id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_event(row) for row in rows]


store = EventStore()
