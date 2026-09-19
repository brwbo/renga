"""Who is in which room. Each team has its own channel and a lead. The pm
sits in the meeting room and delegates to other teams by handing the work to
their lead, who splits it across the team.

The brains (pydantic ai agents on modal) are not wired yet; for now an agent
is a name, a role and the letters on its avatar."""

from pydantic import BaseModel, Field


class Team(BaseModel):
    id: str  # also the channel its chat lives in
    name: str
    purpose: str
    lead: str


class Agent(BaseModel):
    id: str
    name: str
    role: str
    team: str
    initials: str = Field(min_length=1, max_length=2)


TEAMS: list[Team] = [
    Team(id="main", name="meeting", lead="pm",
         purpose="listens to the meeting, keeps the notes, hands work out"),
    Team(id="design", name="design", lead="director",
         purpose="turns what was said into material: scripts, posts, visuals"),
]

ROSTER: list[Agent] = [
    Agent(id="pm", name="pm", team="main", initials="pm",
          role="runs the meeting room, splits the work and delegates it to teams"),
    Agent(id="transcript", name="transcript", team="main", initials="tr",
          role="live speech to text, with speaker labels"),
    Agent(id="visual", name="visual", team="main", initials="vi",
          role="reads screen shares and slides"),
    Agent(id="notes", name="notes", team="main", initials="no",
          role="running summary, decisions and action items"),
    Agent(id="actions", name="actions", team="main", initials="ac",
          role="starts on action items and leaves drafts"),
    Agent(id="director", name="director", team="design", initials="di",
          role="leads design: takes the brief from the pm and splits it across the team"),
    Agent(id="copy", name="copy", team="design", initials="co",
          role="headlines, posts, blog drafts and ad copy"),
    Agent(id="video", name="video", team="design", initials="vd",
          role="video scripts: hook, scenes, voiceover, call to action"),
    Agent(id="visuals", name="visuals", team="design", initials="vs",
          role="thumbnails, slides and social images"),
    Agent(id="brand", name="brand", team="design", initials="br",
          role="checks everything against the brand voice before it goes back"),
]

TEAM_BY_ID = {t.id: t for t in TEAMS}
BY_ID = {a.id: a for a in ROSTER}


def can_speak_in(agent_id: str, channel: str) -> bool:
    """An agent speaks in its own team's room. The pm can speak anywhere,
    because delegating means walking into the other team's room."""
    agent = BY_ID.get(agent_id)
    return bool(agent) and channel in TEAM_BY_ID and (agent.team == channel or agent_id == "pm")
