"""A design team at work. Every member is a pydantic ai agent, and every hand-
off between them is a typed model: the lead turns a brief into a Plan, each
specialist returns Work, and the lead signs it off with a Review. What the
room sees is a stream of Lines, each one a post to renga's api.

    brief -> lead: Plan -> specialists, a wave at a time: Work
          -> lead: Review -> one round of revisions if needed -> done

This module knows nothing about modal: inside.py runs a Crew in a team's
sandbox and sandbox.py hosts it."""

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models import Model

from .presets import Preset, agent_id
from .roles import ROLES, RoleId

DEFAULT_MODEL = "anthropic:claude-sonnet-5"


# ---- the hand-offs ---------------------------------------------------------
class Ask(BaseModel):
    """Something only a person can answer. The work goes ahead on a stated
    assumption; the question waits in the room for you."""

    text: str = Field(description="one question")
    options: list[str] = Field(default_factory=list, max_length=5,
                               description="short answers the person can click, e.g. "
                                           "'yes' or 'a case study link'. never more questions")


class Assignment(BaseModel):
    role: RoleId
    task: str = Field(description="what this person should make, and what it's for")
    after: list[RoleId] = Field(default_factory=list,
                                description="roles whose work this needs before it can start")


class Plan(BaseModel):
    say: str = Field(description="one or two short lines to the room: who's doing what")
    assignments: list[Assignment] = Field(min_length=1)


class Work(BaseModel):
    say: str = Field(description="one or two short lines to the room: what you made")
    deliverable: str = Field(description="the work itself, in markdown")
    ask: Ask | None = None


class Note(BaseModel):
    role: RoleId
    note: str = Field(description="the problem, specifically, not the solution")


class Review(BaseModel):
    say: str = Field(description="one or two short lines to the room")
    approved: bool
    notes: list[Note] = Field(default_factory=list)


class Line(BaseModel):
    """One post into a renga room."""

    agent_id: str
    channel: str
    kind: Literal["chat", "announce_start", "announce_done", "task", "question", "delegate"]
    text: str
    to: str | None = None  # for a delegate line: the room it goes to
    data: dict | None = None
    options: list[str] = Field(default_factory=list)

    def request(self) -> tuple[str, dict]:
        """The path and body that post this line to renga."""
        if self.kind == "delegate":
            return "/api/delegate", {"from_agent": self.agent_id, "room": self.to,
                                     "text": self.text, "data": self.data}
        if self.kind == "question":
            return "/api/questions", {"agent_id": self.agent_id, "channel": self.channel,
                                      "text": self.text, "options": self.options,
                                      "blocking": False}
        return "/api/say", {"agent_id": self.agent_id, "channel": self.channel,
                            "kind": self.kind, "text": self.text, "to": self.to,
                            "data": self.data}


def waves(assignments: list[Assignment]) -> list[list[Assignment]]:
    """Group the assignments so each wave only waits on earlier waves.
    Raises ValueError on a cycle."""
    left, done, out = list(assignments), set(), []
    while left:
        ready = [a for a in left if set(a.after) <= done]
        if not ready:
            raise ValueError("the assignments wait on each other in a circle")
        out.append(ready)
        done |= {a.role for a in ready}
        left = [a for a in left if a not in ready]
    return out


# ---- the team --------------------------------------------------------------
HOUSE_RULES = """\
## the room
you work in a group chat with the rest of your team. `say` is what you post:
one or two short, plain lowercase lines, the way a person would write in a
chat. the work itself goes in `deliverable`. nothing is sent, posted or
published: everything is a draft for a person to approve. when something you
need is missing, make your best assumption, state it in the work and put the
question in `ask` instead of stopping."""


class Crew:
    def __init__(self, preset: Preset, room: str | None = None,
                 model: Model | str | None = None, ids: dict[str, str] | None = None):
        """`ids` maps each role to its agent id in renga, for a room whose
        agents aren't named `<preset>-<role>`."""
        self.preset = preset
        self.room = room or preset.id
        self.lead = preset.lead
        self.ids = ids or {}
        model = model or os.environ.get("RENGA_MODEL", DEFAULT_MODEL)
        self.members = {m.role: Agent(model, output_type=Work, name=m.role,
                                      instructions=self._instructions(m.role),
                                      defer_model_check=True)
                        for m in preset.members}
        self.planner = Agent(model, output_type=Plan, name=f"{self.lead}:plan",
                             instructions=self._instructions(self.lead, lead="plan"),
                             defer_model_check=True)
        self.reviewer = Agent(model, output_type=Review, name=f"{self.lead}:review",
                              instructions=self._instructions(self.lead, lead="review"),
                              defer_model_check=True)
        self.planner.output_validator(self._check_plan)

    def id(self, role: str) -> str:
        return self.ids.get(role) or agent_id(self.preset.id, role)

    def _instructions(self, role: str, lead: str | None = None) -> str:
        me = ROLES[role]
        others = "\n".join(f"- {r.name}: {r.does}" for r in self.preset.roles() if r.id != role)
        text = (f"{me.instructions()}\n\n## you\n\n{self.preset.member(role).character().voice()}\n\n"
                f"## your team\n\nyou're the {me.name} in #{self.room}, a design team that "
                f"does {self.preset.does}. the lead is the {ROLES[self.lead].name}. "
                f"the others:\n{others}\n\n{HOUSE_RULES}")
        if lead == "plan":
            text += ("\n\n## now: plan\n\nyou lead this room. split the brief into assignments, "
                     "one per person, only for the people the work needs. use `after` for work "
                     "that needs someone else's first: words before visuals, research before both. "
                     + ("you don't produce the work yourself." if role == "creative-director"
                        else "you can assign yourself too."))
        elif lead == "review":
            text += ("\n\n## now: review\n\nreview the team's work against the brief, not your "
                     "taste. approve it, or leave a note for each person whose work needs "
                     "another pass. name the problem and let them solve it.")
        return text

    def _check_plan(self, plan: Plan) -> Plan:
        team = {m.role for m in self.preset.members}
        roles = [a.role for a in plan.assignments]
        if strangers := sorted(set(roles) - team):
            raise ModelRetry(f"{', '.join(strangers)} isn't on this team. "
                             f"the team is: {', '.join(sorted(team))}")
        if len(set(roles)) != len(roles):
            raise ModelRetry("give each person one assignment")
        if bad := sorted({r for a in plan.assignments for r in a.after} - set(roles)):
            raise ModelRetry(f"`after` names {', '.join(bad)}, who has no assignment")
        try:
            waves(plan.assignments)
        except ValueError as err:
            raise ModelRetry(str(err)) from err
        return plan

    def _line(self, role: str, kind: str, text: str, **kw) -> Line:
        return Line(agent_id=self.id(role), channel=self.room, kind=kind, text=text, **kw)

    async def _work(self, role: str, prompt: str) -> Work:
        return (await self.members[role].run(prompt)).output

    def _done(self, role: str, work: Work) -> list[Line]:
        lines = [self._line(role, "announce_done", work.say,
                            data={"deliverable": work.deliverable})]
        if work.ask:
            lines.append(self._line(role, "question", work.ask.text, options=work.ask.options))
        return lines

    async def run(self, brief: str) -> AsyncIterator[Line]:
        yield self._line(self.lead, "announce_start", "reading the brief")
        plan = (await self.planner.run(f"the brief:\n\n{brief}")).output
        yield self._line(self.lead, "chat", plan.say, data={"plan": plan.model_dump()})

        done: dict[str, Work] = {}
        for wave in waves(plan.assignments):
            for a in wave:
                yield self._line(self.lead, "task", a.task, to=self.id(a.role))
            prompts = [self._brief(brief, a.task, {f"from the {ROLES[r].name}": done[r]
                                                   for r in a.after})
                       for a in wave]
            results = await asyncio.gather(*(self._work(a.role, p)
                                             for a, p in zip(wave, prompts)))
            for a, work in zip(wave, results):
                done[a.role] = work
                for line in self._done(a.role, work):
                    yield line

        review = (await self.reviewer.run(self._brief(
            brief, "review the work", {f"from the {ROLES[r].name}": w for r, w in done.items()}))).output
        yield self._line(self.lead, "chat", review.say, data={"review": review.model_dump()})
        notes = [n for n in review.notes if n.role in done]
        if not review.approved and notes:
            for n in notes:
                yield self._line(self.lead, "task", n.note, to=self.id(n.role))
            results = await asyncio.gather(*(
                self._work(n.role, self._brief(brief, f"the lead's note on your work: {n.note}",
                                               {"your last version": done[n.role]}))
                for n in notes))
            for n, work in zip(notes, results):
                done[n.role] = work
                for line in self._done(n.role, work):
                    yield line

        yield self._line(self.lead, "announce_done", f"done: {len(done)} pieces ready for you to look at",
                         data={"deliverables": {r: w.deliverable for r, w in done.items()}})

    @staticmethod
    def _brief(brief: str, task: str, inputs: dict[str, Work]) -> str:
        parts = [f"the brief:\n\n{brief}", f"your task:\n\n{task}"]
        parts += [f"{label}:\n\n{w.deliverable}" for label, w in inputs.items()]
        return "\n\n---\n\n".join(parts)
