"""A presentation, from the visualiser's side. The extension says when
someone starts presenting and when they stop. In between, the visualiser
reads each slide quietly; when it's over, everything it found goes into one
notes file, posted in the meeting for the project manager to brief from."""

from typing import Any

START, DONE = "start", "done"


def since_start(events: list[dict[str, Any]], eyes: str) -> list[dict[str, Any]]:
    """The visualiser's events since the presentation started."""
    mine = [e for e in events if e["from"] == eyes]
    start = max((i for i, e in enumerate(mine) if (e.get("data") or {}).get("deck") == START), default=-1)
    return mine[start + 1:]


def presenting(events: list[dict[str, Any]], eyes: str) -> bool:
    """Someone started presenting, and the notes aren't out yet."""
    marks = [d["deck"] for e in events if e["from"] == eyes and (d := e.get("data") or {}).get("deck")]
    return bool(marks) and marks[-1] == START


def unread(events: list[dict[str, Any]], eyes: str) -> set[int]:
    """Slides looked at since the start that the visualiser hasn't read yet."""
    deck = since_start(events, eyes)
    shown = {d["slide"] for e in deck if e["kind"] == "tool_result" and (d := e.get("data") or {}).get("slide")}
    read = {d["slide"] for e in deck if e["kind"] == "chat" and (d := e.get("data") or {}).get("slide")}
    return shown - read


def notes(events: list[dict[str, Any]], eyes: str) -> str:
    """The notes file: what the visualiser found on each slide, in slide
    order, the latest reading of a slide shown twice. Empty when it found
    nothing worth using on any of them."""
    found: dict[int, str] = {}
    for e in since_start(events, eyes):
        d = e.get("data") or {}
        if e["kind"] == "chat" and d.get("slide") and d.get("notes"):
            found[d["slide"]] = d["notes"]
    if not found:
        return ""
    return "# notes on the slides\n\n" + "\n\n".join(f"## slide {n}\n\n{found[n]}" for n in sorted(found)) + "\n"
