"""Who is where. A team works on one repo and has several rooms; each room is
a channel with its own agents and a lead. The teams below are built in; the
ones made from the teams page live in the db (teams.py) and are merged in by
the lookups at the bottom.

The pm sits in the meeting room and delegates to another room in its team by
handing the work to that room's lead, who splits it across the room.

An agent made from the agent library (design/roles.py) remembers which role
it came from in `template`. Those are the ones with brains: pydantic ai
agents hosted in modal sandboxes (design/sandbox.py). The design teams
(design/presets.py) each get a room here, made from the library. In the
built-in meeting room the transcript is a listener, with no brains: it posts
what's said on the call. The pm has brains, as a project manager that reads
it, answers you and routes work to #design; the rest don't yet. Workflows
(workflows.py) set up whole rooms of library agents in any team. aurelia is
a built-in copy of renga's rooms and agents (MIRRORS), reading its own
company file as its context."""

from functools import cache
from typing import Literal

from pydantic import BaseModel, Field

from .design.jobs import logfire_id
from .design.presets import PRESETS_BY_ID, agent_id
from .design.roles import ROLES

# What an agent takes in from outside the chat, through the chrome extension:
# meet's captions, or whatever tab you're looking at.
Sense = Literal["captions", "screen"]


class Team(BaseModel):
    id: str
    name: str
    repo: str  # owner/name on github
    purpose: str


class Room(BaseModel):
    id: str  # also the channel its chat lives in, unique across teams
    team: str
    name: str
    purpose: str
    lead: str | None = None


class Agent(BaseModel):
    id: str
    name: str
    role: str
    room: str
    initials: str = Field(min_length=1, max_length=2)
    senses: list[Sense] = Field(default_factory=list)
    template: str | None = None  # the library role it was made from, if any
    traits: list[str] = Field(default_factory=list)


def from_library(role: str, id: str, room: str, name: str | None = None,
                 traits: list[str] = ()) -> Agent:
    """An agent made from a library role."""
    r = ROLES[role]
    return Agent(id=id, name=name or r.name, role=r.does, room=room, initials=r.initials,
                 senses=list(r.senses), template=role, traits=list(traits))


TEAMS: list[Team] = [
    Team(id="renga", name="renga", repo="brwbo/renga",
         purpose="the meeting copilot: listens, takes notes, turns talk into material"),
    Team(id="rowbo", name="rowbo.ai", repo="brwbo/rowbo.ai",
         purpose="the rowbo.ai site"),
    Team(id="aurelia", name="aurelia", repo="brwbo/renga",
         purpose="aurelia bank: turns calls and the github trail into marketing drafts"),
]

# Built-in teams that are a copy of another built-in team: the same rooms and
# agents, each id prefixed with the team's (`aurelia-meeting`, `aurelia-pm`),
# so they work the same way. Changing renga changes them too.
MIRRORS: dict[str, str] = {"aurelia": "renga"}

# The context doc a built-in team's agents always read, from the repo. One
# written from the ui (teams.py) takes its place.
CONTEXT_FILES: dict[str, str] = {"aurelia": "docs/company.md"}

ROOMS: list[Room] = [
    Room(id="main", team="renga", name="meeting", lead="pm",
         purpose="listens to the meeting, keeps the notes, hands work out"),
    Room(id="rowbo-general", team="rowbo", name="general",
         purpose="everything about the site, until it needs its own room"),
]

ROSTER: list[Agent] = [
    Agent(id="pm", name="pm", room="main", initials="pm", template="project-manager",
          role="runs the meeting room, splits the work and delegates it to other rooms"),
    Agent(id="transcript", name="transcript", room="main", initials="tr", senses=["captions"],
          template="listener",
          role="live speech to text, with speaker labels"),
    Agent(id="visual", name="visual", room="main", initials="vi", senses=["screen"],
          role="reads screen shares, slides and whatever tab you're on"),
    Agent(id="notes", name="notes", room="main", initials="no",
          role="running summary, decisions and action items"),
    Agent(id="actions", name="actions", room="main", initials="ac",
          role="starts on action items and leaves drafts"),
]

# renga's rooms: the meeting, and one design crew the pm hands material to.
# Every team also gets a #logfire room for the traces (_logfire below). The crew is the brand-campaign line-up; the other presets stay in the
# library as workflows, to set up in a team when one is wanted.
DESIGN = PRESETS_BY_ID["brand-campaign"]
ROOMS.insert(1, Room(id="design", team="renga", name="design",
                     lead=agent_id("design", DESIGN.lead),
                     purpose="turns what the meeting decides into material: copy, visuals, social"))
ROSTER += [from_library(m.role, agent_id("design", m.role), "design", traits=m.traits)
           for m in DESIGN.members]

# Agents a new team can start with, one per sense.
STARTERS: dict[Sense, dict] = {
    "screen": {"name": "visual", "initials": "vi",
               "role": "reads whatever tab you're on, through the extension"},
    "captions": {"name": "transcript", "initials": "tr",
                 "role": "hears meet calls through their live captions"},
}


# ---- lookups over the built-in teams and the ones made on the teams page --
def _made():
    from .teams import store
    return store.all()


def _removed() -> dict[str, set[str]]:
    """Built-in teams and agents deleted from the ui. They stay in the code
    above, so deleting one is a note in the db that hides it."""
    from .teams import store
    return store.removed()


@cache
def _mirrors() -> tuple[list[Room], list[Agent]]:
    """The rooms and agents of the built-in teams in MIRRORS: a copy of each
    one's source team, room and agent ids prefixed with the team's. A room is
    named after its source's name (`aurelia-meeting`), an agent after its
    source's id (`aurelia-pm`, `aurelia-design-copywriter`)."""
    rooms, agents = [], []
    for team_id, source in MIRRORS.items():
        ids = {r.id: f"{team_id}-{r.name}" for r in ROOMS if r.team == source}
        moved = [a for a in ROSTER if a.room in ids]
        who = {a.id: f"{team_id}-{a.id}" for a in moved}
        rooms += [r.model_copy(update={"id": ids[r.id], "team": team_id, "lead": who.get(r.lead)})
                  for r in ROOMS if r.id in ids]
        agents += [a.model_copy(update={"id": who[a.id], "room": ids[a.room]}) for a in moved]
    return rooms, agents


def all_teams() -> list[Team]:
    gone = _removed()["team"]
    return [t for t in TEAMS if t.id not in gone] + [t for t, _, _ in _made()]


def _logfire(teams: list[Team]) -> list[Room]:
    """Every team's #logfire room, where its logfire agent posts the traces:
    each hand-off and agent run, how long it took and what it cost."""
    return [Room(id=logfire_id(t.id), team=t.id, name="logfire",
                 purpose="the traces: every hand-off and agent run, how long it took and what it cost")
            for t in teams]


def all_rooms(team: str | None = None) -> list[Room]:
    gone = _removed()["team"]
    from .teams import store
    rooms = ([r for r in ROOMS + _mirrors()[0] if r.team not in gone]
             + [r for _, rs, _ in _made() for r in rs]
             + store.added_rooms())
    taken = {r.id for r in rooms}  # a room someone made called logfire stays theirs
    rooms += [r for r in _logfire(all_teams()) if r.id not in taken]
    return [r for r in rooms if team is None or r.team == team]


def all_agents() -> list[Agent]:
    from .teams import store
    gone = _removed()["agent"]
    rooms = {r.id for r in all_rooms()}
    watchers = [Agent(id=r.id, name="logfire", room=r.id, initials="lf",
                      role="reads the logfire traces and posts each run: time, tokens, errors")
                for r in _logfire(all_teams())]
    everyone = (ROSTER + _mirrors()[1] + [a for _, _, agents in _made() for a in agents]
                + store.added() + watchers)
    return [a for a in everyone if a.id not in gone and a.room in rooms]


def team(team_id: str) -> Team | None:
    return next((t for t in all_teams() if t.id == team_id), None)


def room(room_id: str) -> Room | None:
    return next((r for r in all_rooms() if r.id == room_id), None)


def agent(agent_id: str) -> Agent | None:
    return next((a for a in all_agents() if a.id == agent_id), None)


def can_speak_in(agent_id: str, channel: str) -> bool:
    """An agent speaks in its own room. A project manager can speak in any
    room of its team, because delegating means walking into the other room."""
    who, where = agent(agent_id), room(channel)
    if not who or not where:
        return False
    pm = who.template == "project-manager"
    return who.room == channel or (pm and where.team == room(who.room).team)
