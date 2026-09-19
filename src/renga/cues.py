"""When someone on the call is showing something. A caption line like "as you
can see" or "if you look at this slide" means there's something on screen
worth seeing, so the team's screen agent should look at it. The server spots
the cue; the chrome extension, which can see the call, takes the screenshot.

At most one look per room every GAP seconds, so a whole walkthrough of
"and here you can see..." doesn't become a screenshot per sentence."""

import re
import threading
import time

GAP = 20.0

_THING = r"(slide|deck|chart|graph|diagram|dashboard|screen|page|table|numbers|mock ?up|design|demo|doc)"
LOOK = re.compile("|".join([
    r"\bas you (can )?see\b",
    r"\b(if|when) you look\b",
    r"\blook(ing)? at (this|that|these|here|my|the)\b",
    r"\b(take|have) a look\b",
    r"\byou can see (here|this|that|these|on|in|the)\b",
    r"\bon (my|the|your) screen\b",
    r"\b(i'?m|i am|let me|i'?ll) (share|sharing|show|showing|pull up|pulling up)\b",
    r"\bscreen ?shar(e|ing)\b",
    r"\bcan (you|everyone) see (my|this|it|that)\b",
    rf"\b(this|the next|next|that|on this|here'?s the|here is the) {_THING}\b",
]), re.IGNORECASE)


def cue(text: str) -> str | None:
    """The words in a caption line that mean something's being shown."""
    m = LOOK.search(text or "")
    return m.group(0) if m else None


class Looks:
    """When each room last looked, for the GAP."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def due(self, room: str) -> bool:
        """True, and starts the gap, when the room may look again."""
        now = time.monotonic()
        with self._lock:
            if now - self._last.get(room, -GAP) < GAP:
                return False
            self._last[room] = now
            return True


looks = Looks()
