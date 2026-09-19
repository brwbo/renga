"""The call's audio, for a listener hearing it without captions. The chrome
extension records the meet tab and posts it here a chunk at a time; the
agents' host (design/sandbox.py listen) takes the chunks, one room at a time
and in order, and has the listener's ears (design/ears.py) transcribe them.

Chunks wait in memory, never on disk or in the event log. At most QUEUE wait
per room: past that the oldest go, so a host that's down doesn't pile up
audio forever."""

import base64
import binascii
import threading
from collections import deque

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import agents

QUEUE = 200  # about ten minutes of a call, cut at its pauses
TYPES = {"audio/wav"}

router = APIRouter()


class HearIn(BaseModel):
    """A chunk of the call, from the extension, for the team's captions agent."""

    agent_id: str
    audio: str = Field(min_length=1, max_length=3_000_000)  # base64
    mime: str = "audio/wav"


class NextIn(BaseModel):
    busy: list[str] = Field(default_factory=list)  # rooms still transcribing the last chunk


class Heard:
    def __init__(self) -> None:
        self._rooms: dict[str, deque[dict]] = {}
        self._lock = threading.Lock()

    def add(self, room: str, chunk: dict) -> int:
        with self._lock:
            q = self._rooms.setdefault(room, deque(maxlen=QUEUE))
            q.append(chunk)
            return len(q)

    def next(self, busy: set[str]) -> list[dict]:
        """The oldest chunk of each room that isn't busy, taken off the queue."""
        with self._lock:
            return [q.popleft() for room, q in self._rooms.items() if q and room not in busy]


heard = Heard()


@router.post("/api/hear", status_code=202)
def hear(body: HearIn) -> dict:
    who = agents.agent(body.agent_id)
    if not who:
        raise HTTPException(404, f"no agent called {body.agent_id!r}")
    if "captions" not in who.senses:
        raise HTTPException(403, f"{who.name} doesn't hear the call")
    if body.mime not in TYPES:
        raise HTTPException(422, f"the audio should be one of {sorted(TYPES)}")
    try:
        base64.b64decode(body.audio, validate=True)
    except binascii.Error as err:
        raise HTTPException(422, "the audio isn't valid base64") from err
    waiting = heard.add(who.room, {"room": who.room, "agent_id": who.id,
                                   "audio": body.audio, "mime": body.mime})
    return {"room": who.room, "waiting": waiting}


@router.post("/api/heard/next")
def next_chunks(body: NextIn) -> list[dict]:
    """For the agents' host: the next chunk of each room it isn't busy in."""
    return heard.next(set(body.busy))
