"""Fans new events out to connected websocket clients. The log in db.py is the source of truth; this is just the live
tail. `emit` is the one path every event takes, human or agent."""

import asyncio
from typing import Any

import logfire
from fastapi import WebSocket

from .events import Event


class Bus:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:
                await self.disconnect(ws)


bus = Bus()


async def emit(
    channel: str,
    kind: str,
    from_: str = "admin",
    to: str | None = None,
    text: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict:
    """Append to the log, then push to whoever is listening. The span records
    the shape of the conversation (who to whom, which kind), never the text."""
    from .db import store

    with logfire.span("{kind} {channel}", kind=kind, channel=channel,
                      sender=from_, recipient=to,
                      chars=len(text) if text else 0):
        event = store.append(channel, kind, from_=from_, to=to, text=text, data=data)
        Event.model_validate(event)
        await bus.broadcast(event)
    return event
