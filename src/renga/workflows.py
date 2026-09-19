"""Premade workflows: rooms of library agents that work together, set up in
any team in one go. Starting one makes its rooms and agents; the agents' host
(design/sandbox.py listen) runs them.

The meeting workflow is the connector between a meeting and the teams: the
listener hears the call and posts it in the meeting room as the transcript;
the project manager reads it, answers you in the chat, and hands what needs
doing to the marketing room, whose lead splits it across the room and has it done. Design
is part of marketing: one room does the copy, the visuals and the social."""

from pydantic import BaseModel, Field, model_validator

from .agents import Agent, Room, from_library
from .design.presets import PRESETS, Member
from .design.roles import RoleId
from .teams import slug


class RoomPlan(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9-]+$")
    purpose: str
    lead: RoleId
    members: list[Member] = Field(min_length=1)

    @model_validator(mode="after")
    def _lead_is_in_it(self) -> "RoomPlan":
        if self.lead not in {m.role for m in self.members}:
            raise ValueError(f"#{self.name}'s lead isn't in the room")
        return self


class Workflow(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    does: str
    how: list[str] = Field(default_factory=list)  # the steps, for the library page
    rooms: list[RoomPlan] = Field(min_length=1)

    def build(self, team: str) -> tuple[list[Room], list[Agent]]:
        """The rooms and agents this workflow makes in a team. Ids follow the
        team: `<team>-<room>` for rooms, `<team>-<room>-<role>` for agents."""
        rooms, agents = [], []
        for plan in self.rooms:
            room_id = f"{team}-{plan.name}"
            ids = {m.role: f"{room_id}-{slug(m.role)}" for m in plan.members}
            rooms.append(Room(id=room_id, team=team, name=plan.name,
                              purpose=plan.purpose, lead=ids[plan.lead]))
            agents += [from_library(m.role, ids[m.role], room_id, traits=m.traits)
                       for m in plan.members]
        return rooms, agents


def _m(role: str, *traits: str) -> Member:
    return Member(role=role, traits=list(traits))


MEETING = Workflow(
    id="meeting-to-marketing", name="meeting to marketing",
    does="a listener posts the meeting's transcript, a project manager reads it, answers you "
         "and turns what needs doing into briefs for the marketing room, who do the work",
    how=["the listener posts what's said in the meeting, through the chrome extension",
         "when the meeting pauses, the project manager reads it and picks out what needs doing",
         "talk to the project manager in the meeting chat and it answers you",
         "the project manager hands each action to #marketing as a brief",
         "the marketing lead splits it across the room, and the drafts come back to you",
         "alongside, the note-taker keeps the notes, and the visualiser says what's on screen "
         "and draws what the meeting describes"],
    rooms=[
        RoomPlan(name="meeting", lead="project-manager",
                 purpose="hears the meeting and hands out what needs doing",
                 members=[_m("listener"), _m("project-manager", "stoic", "methodical", "leader", "judging"),
                          _m("note-taker"), _m("visualiser")]),
        RoomPlan(name="marketing", lead="marketing-strategist",
                 purpose="campaigns, copy, visuals, social and content",
                 members=[_m("marketing-strategist", "intense", "big-picture", "leader", "thinking"),
                          _m("copywriter", "sassy", "fast-shipper", "extrovert", "risk-taker"),
                          _m("graphic-designer", "stoic", "perfectionist", "introvert", "thinking"),
                          _m("motion-designer", "enthusiastic", "chaotic-creative", "extrovert", "risk-taker"),
                          _m("social-media-designer", "enthusiastic", "fast-shipper", "collaborator", "optimist"),
                          _m("content-strategist", "nurturing", "methodical", "mentor", "judging")]),
    ],
)

# Each design team is also a one-room workflow, so any team can have one.
WORKFLOWS: list[Workflow] = [MEETING] + [
    Workflow(id=p.id, name=p.id.replace("-", " "), does=p.does,
             rooms=[RoomPlan(name=p.id, purpose=p.does, lead=p.lead, members=p.members)])
    for p in PRESETS
]
WORKFLOWS_BY_ID: dict[str, Workflow] = {w.id: w for w in WORKFLOWS}
