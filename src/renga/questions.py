"""Questions an agent asks when it hits a roadblock. The same idea as
agentville's question queue: the agent parks the work, the question shows in
the chat with its options as buttons, and the answer unparks it."""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .db import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ts INTEGER NOT NULL,
    channel TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    answered INTEGER NOT NULL DEFAULT 0,
    answer TEXT,
    data TEXT NOT NULL
);
"""


class QuestionIn(BaseModel):
    agent_id: str
    text: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list, max_length=5)
    blocking: bool = True
    channel: str = "main"


class QuestionStore:
    def __init__(self, path: Path = DB_PATH):
        self._path = path
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, check_same_thread=False)

    @staticmethod
    def _row(row: tuple) -> dict[str, Any]:
        id_, channel, agent_id, answered, answer, data = row
        return {"id": id_, "channel": channel, "agent_id": agent_id,
                "answered": bool(answered), "answer": answer, **json.loads(data)}

    def add(self, q: QuestionIn) -> dict[str, Any]:
        data = json.dumps({"text": q.text, "options": q.options, "blocking": q.blocking})
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO questions (created_ts, channel, agent_id, data) VALUES (?, ?, ?, ?)",
                (int(time.time() * 1000), q.channel, q.agent_id, data))
            qid = cur.lastrowid
        return self.get(qid)

    def get(self, qid: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id, channel, agent_id, answered, answer, data "
                               "FROM questions WHERE id = ?", (qid,)).fetchone()
        return self._row(row) if row else None

    def open(self, channel: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT id, channel, agent_id, answered, answer, data FROM questions WHERE answered = 0"
        params: list[Any] = []
        if channel:
            query += " AND channel = ?"
            params.append(channel)
        with self._connect() as conn:
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
        return [self._row(r) for r in rows]

    def answer(self, qid: int, value: str) -> bool:
        """False when there is no such open question, so it can't be answered twice."""
        with self._lock, self._connect() as conn:
            cur = conn.execute("UPDATE questions SET answered = 1, answer = ? "
                               "WHERE id = ? AND answered = 0", (value, qid))
            return cur.rowcount == 1


store = QuestionStore()
