"""What the host sends into a sandbox: one typed Job, built from what renga
says about a room and who is in it. A sandbox never talks to renga's
database, so everything the agents need travels in the job.

A room has brains when its lead came from the library:
- a design or marketing lead runs a crew (crew.py) on each brief it's handed
- a project manager runs the router (router.py) on what's said in the meeting
A listener from the library in a project manager's room has brains too: it
runs listener.py on what's said and sends the project manager each action.
So do its aides: a note-taker keeps the notes (notes.py) and a visualiser
says what's on screen and draws what's described (visualiser.py). Nobody
reads the aides' posts as the meeting, so they never wake anyone."""

from typing import Literal, get_args

from pydantic import BaseModel, Field

from .presets import Member, Preset
from .roles import DesignRoleId
from .router import Target
from .visualiser import Screen

CREW_ROLES = set(get_args(DesignRoleId))
AIDES = ("note-taker", "visualiser")


class Job(BaseModel):
    kind: Literal["crew", "router", "listener", "notes", "eyes"]
    room: str
    # a crew
    team: Preset | None = None
    ids: dict[str, str] = Field(default_factory=dict)  # role -> agent id
    brief: str = ""
    traceparent: str = ""  # the hand-off's trace, so the crew's run joins it
    watch: bool = False    # post each agent run into a #logfire room, when there is one
    context: str = ""      # the team's context doc, which every agent reads
    # the router and the listener
    pm: str = ""
    listener: str = ""
    targets: list[Target] = Field(default_factory=list)
    seen: list[str] = Field(default_factory=list)
    new: list[str] = Field(default_factory=list)
    # the aides
    me: str = ""
    notes: str = ""               # the note-taker's last notes
    screen: Screen | None = None  # the look that woke the visualiser


def _lead(room: dict, agents: list[dict]) -> dict | None:
    return next((a for a in agents if a["id"] == room.get("lead")), None)


def brains(room: dict, agents: list[dict]) -> Literal["crew", "router"] | None:
    lead = _lead(room, agents)
    template = lead and lead.get("template")
    if template == "project-manager":
        return "router"
    if template in CREW_ROLES:
        return "crew"
    return None


def listener_of(room: dict, agents: list[dict]) -> dict | None:
    """The room's listener, when it's a project manager's room with one."""
    if brains(room, agents) != "router":
        return None
    return next((a for a in agents if a["room"] == room["id"] and a.get("template") == "listener"), None)


def aide(room: dict, agents: list[dict], role: str) -> dict | None:
    """The room's note-taker or visualiser, when it's a project manager's room with one."""
    if brains(room, agents) != "router":
        return None
    return next((a for a in agents if a["room"] == room["id"] and a.get("template") == role), None)


def aides(room: dict, agents: list[dict]) -> set[str]:
    return {a["id"] for r in AIDES if (a := aide(room, agents, r))}


def crew_job(room: dict, agents: list[dict], brief: str, traceparent: str = "") -> Job:
    """The room's library agents as a crew, one per role, led by its lead."""
    members: dict[str, dict] = {}
    for a in agents:
        if a["room"] == room["id"] and a.get("template") in CREW_ROLES:
            members.setdefault(a["template"], a)  # a second copywriter sits this one out
    team = Preset(id=room["id"], does=room.get("purpose") or f"the work of #{room['name']}",
                  members=[Member(role=r, traits=a.get("traits") or []) for r, a in members.items()],
                  lead_role=_lead(room, agents)["template"])
    return Job(kind="crew", room=room["id"], team=team, brief=brief, traceparent=traceparent,
               ids={r: a["id"] for r, a in members.items()})


def router_job(room: dict, rooms: list[dict], agents: list[dict],
               events: list[dict], since: int) -> Job:
    """The project manager's view: every other room in the team that can take
    work, what was said before `since`, and what was said after it."""
    names = {a["id"]: a["name"] for a in agents}
    targets = [Target(room=r["id"], name=r["name"], purpose=r.get("purpose", ""),
                      members=[a["name"] for a in agents if a["room"] == r["id"]])
               for r in rooms
               if r["team"] == room["team"] and r["id"] != room["id"] and brains(r, agents) == "crew"]

    lines = _meeting(room, events, names, you=room["lead"], done=("handoff", "handed off"),
                     skip=aides(room, agents))
    return Job(kind="router", room=room["id"], pm=room["lead"], targets=targets,
               seen=[s for i, _, s in lines if i <= since][-40:],
               new=[s for i, _, s in lines if i > since])


def listener_job(room: dict, agents: list[dict], events: list[dict], since: int) -> Job:
    """The listener's view: what was said before `since`, with the actions it
    already sent, and what was said after it."""
    me = listener_of(room, agents)
    names = {a["id"]: a["name"] for a in agents}
    lines = _meeting(room, events, names, done=("task", "sent"), skip=aides(room, agents))
    return Job(kind="listener", room=room["id"], pm=room["lead"], listener=me["id"],
               seen=[s for i, _, s in lines if i <= since][-60:],
               new=[s for i, kind, s in lines if i > since and kind != "task"])


def notes_job(room: dict, agents: list[dict], events: list[dict], since: int) -> Job:
    """The note-taker's view: the notes it last posted, what was said before
    `since`, and what was said after it."""
    me = aide(room, agents, "note-taker")
    names = {a["id"]: a["name"] for a in agents}
    last = next((e for e in reversed(events) if e["channel"] == room["id"] and e["from"] == me["id"]
                 and (e.get("data") or {}).get("deliverable")), None)
    lines = _meeting(room, events, names, done=("task", "sent"), skip=aides(room, agents))
    return Job(kind="notes", room=room["id"], me=me["id"], notes=last["data"]["deliverable"] if last else "",
               seen=[s for i, _, s in lines if i <= since][-60:],
               new=[s for i, kind, s in lines if i > since and kind != "task"])


def eyes_job(room: dict, agents: list[dict], events: list[dict], since: int,
             screen: Screen | None = None) -> Job:
    """The visualiser's view: what was said, with what it already posted as
    `you`, and the look at the screen that woke it, if one did."""
    me = aide(room, agents, "visualiser")
    names = {a["id"]: a["name"] for a in agents}
    lines = _meeting(room, events, names, done=("task", "sent"), you=me["id"],
                     skip=aides(room, agents) - {me["id"]})
    mine = {e["id"] for e in events if e["from"] == me["id"]}
    return Job(kind="eyes", room=room["id"], me=me["id"], screen=screen,
               seen=[s for i, _, s in lines if i <= since or i in mine][-40:],
               new=[s for i, kind, s in lines if i > since and i not in mine and kind != "task"])


def _meeting(room: dict, events: list[dict], names: dict[str, str], done: tuple[str, str],
             you: str | None = None, skip: set[str] = frozenset()) -> list[tuple[int, str, str]]:
    """What's been said in a meeting room, as (event id, kind, `who: text`),
    with the listener's actions to the project manager in it. `you` is who
    reads it; lines of the `done` kind are marked as dealt with. Lines from
    `skip` (the aides) aren't the meeting and are left out."""
    def said(e: dict) -> str:
        who = "you" if e["from"] == you else names.get(e["from"], e["from"])
        mark = f" [{done[1]}]" if e["kind"] == done[0] else ""
        return f"{who}: {e['text']}{mark}"

    return [(e["id"], e["kind"], said(e)) for e in events
            if e["channel"] == room["id"] and e.get("text") and e["from"] not in skip
            and (e["kind"] in ("chat", "handoff", "answer")
                 or (e["kind"] == "task" and e.get("to") == room["lead"]))]
