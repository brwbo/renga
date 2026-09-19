"""Who is where. A team works on one repo and has several rooms; each room is
a channel with its own agents and a lead. The teams below are built in; the
ones made from the teams page live in the db (teams.py) and are merged in by
the lookups at the bottom.

The pm sits in the meeting room and delegates to another room in its team by
handing the work to that room's lead, who splits it across the room.

The brains (pydantic ai agents on modal) are not wired yet; for now an agent
is a name, a role and the letters on its avatar."""

from typing import Literal

from pydantic import BaseModel, Field

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


TEAMS: list[Team] = [
    Team(id="renga", name="renga", repo="brwbo/renga",
         purpose="the meeting copilot: listens, takes notes, turns talk into material"),
    Team(id="rowbo", name="rowbo.ai", repo="brwbo/rowbo.ai",
         purpose="the rowbo.ai site"),
]

ROOMS: list[Room] = [
    Room(id="main", team="renga", name="meeting", lead="pm",
         purpose="listens to the meeting, keeps the notes, hands work out"),
    Room(id="design", team="renga", name="design", lead="director",
         purpose="turns what was said into material: scripts, posts, visuals"),
    Room(id="rowbo-general", team="rowbo", name="general",
         purpose="everything about the site, until it needs its own room"),
]

ROSTER: list[Agent] = [
    Agent(id="pm", name="pm", room="main", initials="pm",
          role="runs the meeting room, splits the work and delegates it to other rooms"),
    Agent(id="transcript", name="transcript", room="main", initials="tr", senses=["captions"],
          role="live speech to text, with speaker labels"),
    Agent(id="visual", name="visual", room="main", initials="vi", senses=["screen"],
          role="reads screen shares, slides and whatever tab you're on"),
    Agent(id="notes", name="notes", room="main", initials="no",
          role="running summary, decisions and action items"),
    Agent(id="actions", name="actions", room="main", initials="ac",
          role="starts on action items and leaves drafts"),
    Agent(id="director", name="director", room="design", initials="di",
          role="leads design: takes the brief from the pm and splits it across the room"),
    Agent(id="copy", name="copy", room="design", initials="co",
          role="headlines, posts, blog drafts and ad copy"),
    Agent(id="video", name="video", room="design", initials="vd",
          role="video scripts: hook, scenes, voiceover, call to action"),
    Agent(id="visuals", name="visuals", room="design", initials="vs",
          role="thumbnails, slides and social images"),
    Agent(id="brand", name="brand", room="design", initials="br",
          role="checks everything against the brand voice before it goes back"),
]

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


def all_teams() -> list[Team]:
    gone = _removed()["team"]
    return [t for t in TEAMS if t.id not in gone] + [t for t, _, _ in _made()]


def all_rooms(team: str | None = None) -> list[Room]:
    gone = _removed()["team"]
    rooms = [r for r in ROOMS if r.team not in gone] + [r for _, rs, _ in _made() for r in rs]
    return [r for r in rooms if team is None or r.team == team]


def all_agents() -> list[Agent]:
    from .teams import store
    gone = _removed()["agent"]
    rooms = {r.id for r in all_rooms()}
    everyone = ROSTER + [a for _, _, agents in _made() for a in agents] + store.added()
    return [a for a in everyone if a.id not in gone and a.room in rooms]


def team(team_id: str) -> Team | None:
    return next((t for t in all_teams() if t.id == team_id), None)


def room(room_id: str) -> Room | None:
    return next((r for r in all_rooms() if r.id == room_id), None)


def agent(agent_id: str) -> Agent | None:
    return next((a for a in all_agents() if a.id == agent_id), None)


def can_speak_in(agent_id: str, channel: str) -> bool:
    """An agent speaks in its own room. The pm can speak in any room of its
    team, because delegating means walking into the other room."""
    who, where = agent(agent_id), room(channel)
    if not who or not where:
        return False
    return who.room == channel or (agent_id == "pm" and where.team == room(who.room).team)
