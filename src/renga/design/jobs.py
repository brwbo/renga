"""What the host sends into a sandbox: one typed Job, built from what renga
says about a room and who is in it. A sandbox never talks to renga's
database, so everything the agents need travels in the job.

A room has brains when its lead came from the library:
- a design or marketing lead runs a crew (crew.py) on each brief it's handed
- a project manager runs the router (router.py) on what's said in the meeting"""

from typing import Literal, get_args

from pydantic import BaseModel, Field

from .presets import Member, Preset
from .roles import DesignRoleId
from .router import Target

CREW_ROLES = set(get_args(DesignRoleId))


class Job(BaseModel):
    kind: Literal["crew", "router"]
    room: str
    # a crew
    team: Preset | None = None
    ids: dict[str, str] = Field(default_factory=dict)  # role -> agent id
    brief: str = ""
    traceparent: str = ""  # the hand-off's trace, so the crew's run joins it
    watch: bool = False    # post each agent run into a #logfire room, when there is one
    # the router
    pm: str = ""
    targets: list[Target] = Field(default_factory=list)
    seen: list[str] = Field(default_factory=list)
    new: list[str] = Field(default_factory=list)


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

    def said(e: dict) -> str:
        who = "you" if e["from"] == room["lead"] else names.get(e["from"], e["from"])
        mark = " [handed off]" if e["kind"] == "handoff" else ""
        return f"{who}: {e['text']}{mark}"

    lines = [e for e in events if e["channel"] == room["id"] and e.get("text")
             and e["kind"] in ("chat", "handoff", "answer")]
    return Job(kind="router", room=room["id"], pm=room["lead"], targets=targets,
               seen=[said(e) for e in lines if e["id"] <= since][-40:],
               new=[said(e) for e in lines if e["id"] > since])
