"""The project manager's brain: the connector between a meeting and the teams.
It reads what's been said in the meeting room since it last looked, decides
what needs doing, and hands each piece to the team room that should do it.
Each hand-off lands with that room's lead, whose crew (crew.py) does the work.

It only hands off work it can brief without guessing. It checks the meeting
and the team's context doc first; what's still missing (a rate, a date, who
it's for) it asks for in the chat, and the work waits until someone answers,
in the chat or on the call.

    meeting lines -> project manager: Routing -> a line in the meeting
                                              -> what it still needs, in the meeting
                                              -> a brief to each team's lead"""

import os
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.models import Model

from .crew import DEFAULT_MODEL, Line, about
from .personality import voice
from .roles import ROLES


class Target(BaseModel):
    """A room the project manager can hand work to."""

    room: str
    name: str
    purpose: str = ""
    members: list[str] = Field(default_factory=list)  # role names, for context


class Handoff(BaseModel):
    room: str = Field(description="the id of the room that should do it")
    brief: str = Field(description="what's needed, why, who asked, any numbers or dates "
                                   "said, and what done looks like")


class Need(BaseModel):
    """Work held back because a brief would have to guess."""

    work: str = Field(description="the piece of work that's waiting, in a few words")
    room: str = Field(description="the id of the room it will go to once you have the answers")
    asks: list[str] = Field(min_length=1, description="each fact you still need, as a short "
                                                      "question the person can answer in a line")


class Routing(BaseModel):
    say: str | None = Field(default=None, description="your line in the chat: your answer when "
                                                      "the person talked to you, and what you "
                                                      "sent where. don't repeat the questions in "
                                                      "`needs`: they're posted as their own list. "
                                                      "empty when there's nothing to say")
    handoffs: list[Handoff] = Field(default_factory=list,
                                    description="work you can brief without guessing any fact")
    needs: list[Need] = Field(default_factory=list,
                              description="work that waits, and what you need to hand it off. "
                                          "only what the meeting and the team's context don't answer")


def asking(need: Need, rooms: dict[str, str]) -> str:
    """How a need reads in the chat."""
    asks = "\n".join(f"- {a}" for a in need.asks)
    return f"before {need.work} goes to #{rooms.get(need.room, need.room)}, i need:\n{asks}"


class Router:
    def __init__(self, room: str, pm: str, targets: list[Target],
                 model: Model | str | None = None,
                 context: str = ""):
        self.room, self.pm, self.targets = room, pm, targets
        model = model or os.environ.get("RENGA_MODEL", DEFAULT_MODEL)
        me = ROLES["project-manager"]
        rooms = "\n".join(f"- `{t.room}` (#{t.name}): {t.purpose or 'no purpose given'}. "
                          f"in it: {', '.join(t.members) or 'nobody yet'}" for t in targets)
        self.agent = Agent(
            model, output_type=Routing, name="project-manager", defer_model_check=True,
            instructions=f"{me.instructions()}\n\n## you\n\n{voice(me.personality)}\n\n"
                         f"## the rooms you can hand work to\n\n{rooms}\n\n"
                         "## the meeting\n\nyou sit in the meeting room. `person:` lines are the "
                         "person using renga, talking to you in the chat: always answer them in "
                         "`say`. the other lines are the call's transcript. `say` is short, "
                         "plain lowercase, the way a person writes in a chat. nothing is sent, posted or published "
                         "outside renga: the teams make drafts for a person to approve. lines "
                         "you've already handed off are marked; never hand the same thing off twice."
                         "\n\n## enough to brief\n\nhand work off only when the team could make it "
                         "without guessing a fact: numbers, rates, prices, dates, names, who it's "
                         "for, where it runs. look in the context doc (below, when there is one) and "
                         "in the meeting first, and never ask for what either already says. whatever is still "
                         "missing goes in `needs`, and that work waits: don't hand it off, and "
                         "don't fill the gap yourself. taste (tone, which option, wording) isn't a "
                         "fact: the team decides it and the person reviews it. your own earlier "
                         "`before … i need:` lines are what you're still waiting on: once the "
                         "person or the call answers, hand that work off with the answers in the "
                         "brief, and don't ask again for what's been answered. what's been "
                         "shown on screen (slides, shared tabs) counts as said in the meeting: "
                         "put its facts in the brief, and don't ask for what the screen showed. "
                         "the visualiser only writes down what's on screen; the design team "
                         "makes the material.\n\n## the brief\n\nbefore you hand work off, read the "
                         "whole meeting, from its first line, and everything shown on screen. the "
                         "brief carries every fact from the session that bears on the work (who "
                         "it's for, the numbers, the names, the before and after, what was decided), "
                         "not only what was said last. the design team sees nothing but your brief."
                         + about(context))
        self.agent.output_validator(self._check)

    def _check(self, routing: Routing) -> Routing:
        known = {t.room for t in self.targets}
        if bad := sorted({h.room for h in [*routing.handoffs, *routing.needs]} - known):
            raise ModelRetry(f"there's no room {', '.join(bad)}. use one of: {', '.join(sorted(known))}")
        return routing

    async def run(self, seen: list[str], new: list[str], slides: list[str] = ()) -> AsyncIterator[Line]:
        """`seen` is what was said before (context), `new` is what to act on,
        `slides` what's been presented, as the visualiser read it."""
        shown = ("what's been shown on screen in this meeting (the slides presented, the tabs "
                 "shared), everything on it, as the visualiser wrote it down:\n\n" + "\n\n".join(slides)
                 + "\n\n" if slides else "")
        prompt = (shown + "the meeting so far, from its first line (context for any brief):\n\n"
                  + ("\n".join(seen) or "(nothing)")
                  + "\n\nsaid since you last looked:\n\n" + "\n".join(new))
        yield Line(agent_id=self.pm, channel=self.room, kind="thinking", text="")
        routing = (await self.agent.run(prompt)).output
        if routing.say:
            yield Line(agent_id=self.pm, channel=self.room, kind="chat", text=routing.say)
        names = {t.room: t.name for t in self.targets}
        for n in routing.needs:
            yield Line(agent_id=self.pm, channel=self.room, kind="chat", text=asking(n, names),
                       data={"need": n.model_dump()})
        for h in routing.handoffs:
            yield Line(agent_id=self.pm, channel=self.room, kind="delegate", to=h.room, text=h.brief)
