"""Who is thinking right now, by room: what the chat shows as moving dots.
Not part of the event log. An agent is marked just before each model call
and unmarked when it next says something in that room, when its job ends,
or after STALE seconds, whichever comes first."""

import threading
import time

STALE = 300.0  # a job that dies without saying so stops showing after this


class Thinking:
    def __init__(self) -> None:
        self._since: dict[tuple[str, str], float] = {}  # (room, agent) -> when marked
        self._lock = threading.Lock()

    def start(self, channel: str, agent: str) -> None:
        with self._lock:
            self._since[(channel, agent)] = time.monotonic()

    def stop(self, channel: str, agent: str | None = None) -> None:
        """One agent done in a room, or everyone in it when `agent` is None."""
        with self._lock:
            for key in [k for k in self._since if k[0] == channel and agent in (None, k[1])]:
                del self._since[key]

    def now(self) -> dict[str, list[str]]:
        cutoff = time.monotonic() - STALE
        out: dict[str, list[str]] = {}
        with self._lock:
            for (channel, agent), since in list(self._since.items()):
                if since < cutoff:
                    del self._since[(channel, agent)]
                else:
                    out.setdefault(channel, []).append(agent)
        return out


thinking = Thinking()
