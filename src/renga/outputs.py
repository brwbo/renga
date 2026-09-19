"""A team's library of finished work: only what the lead signed off, never the
drafts. A design room's run ends with the lead's "done: n pieces" line, which
carries the final text of each piece (crew.Crew.run). Each piece's files are
on the line where its maker posted that exact text, so the final version of
a piece that went back for another pass is the redo, not the first draft."""

import hashlib

from fastapi import APIRouter, HTTPException

from . import agents
from .db import store

router = APIRouter()


def approved(events: list[dict]) -> list[dict]:
    """The signed-off sets in these events, newest first. Each set has the
    room, who signed it off, the brief when there was one, and its pieces."""
    made: dict[tuple[str, str], dict] = {}  # (room, the work's text) -> the line that posted it
    briefs: dict[str, str] = {}  # room -> the last brief handed to it
    sets = []
    for e in sorted(events, key=lambda e: e["id"]):
        data = e.get("data") or {}
        if e["kind"] == "task" and data.get("delegated_from"):
            briefs[e["channel"]] = e.get("text", "")
        if e["kind"] != "announce_done":
            continue
        if isinstance(data.get("deliverable"), str):
            made[(e["channel"], data["deliverable"])] = e
        final = data.get("deliverables")
        if not isinstance(final, dict) or not final:
            continue
        pieces = []
        for role, text in final.items():
            line = made.get((e["channel"], text))
            pieces.append({
                "role": role,
                "by": line["from"] if line else None,
                "said": line.get("text", "") if line else "",
                "deliverable": text,
                "files": (line.get("data") or {}).get("files", []) if line else [],
            })
        sets.append({"id": e["id"], "ts": e["ts"], "room": e["channel"], "lead": e["from"],
                     "brief": briefs.get(e["channel"], ""), "pieces": pieces})
    return sets[::-1]


def kept(f: dict) -> dict:
    """A file as the page shows it. Early runs kept a file's content in the
    event itself; it's written to disk once, under a name from its content,
    so it's served (sandboxed) like every file since."""
    from .main import FILE_NAME, FILE_TYPES, FILES  # at call time: main imports this module

    if f.get("url") or not isinstance(f.get("content"), str) or not FILE_NAME.match(f.get("name", "")):
        return f
    stem, _, ext = f["name"].rpartition(".")
    stored = f"{hashlib.sha256(f['content'].encode()).hexdigest()[:12]}-{stem}.{ext}"
    if not (FILES / stored).exists():
        (FILES / stored).write_text(f["content"])
    return {"name": f["name"], "url": f"/files/{stored}", "type": FILE_TYPES[ext], "size": len(f["content"])}


@router.get("/api/teams/{team_id}/outputs")
def team_outputs(team_id: str) -> list[dict]:
    if not agents.team(team_id):
        raise HTTPException(404, f"no team called {team_id!r}")
    events = [e for r in agents.all_rooms(team_id) for e in store.since(0, r.id)]
    sets = approved(events)
    for s in sets:
        for p in s["pieces"]:
            p["files"] = [kept(f) for f in p["files"]]
    return sets
