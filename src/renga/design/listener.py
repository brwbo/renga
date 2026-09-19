"""The listener's brain: it hears the meeting and says what needs doing. The
captions it posts (through the chrome extension) are the meeting's record;
when the meeting pauses it reads what's new and sends each action it heard
to the project manager, who hands it to a team (router.py).

    meeting lines -> listener: Heard -> an action to the project manager, each"""

import os
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from .crew import DEFAULT_MODEL, Line, about
from .personality import voice
from .roles import ROLES


class Action(BaseModel):
    what: str = Field(description="what needs doing, as one plain instruction")
    who: str = Field(default="", description="who asked for it or took it on, as said. empty if nobody")
    due: str = Field(default="", description="the date or deadline, as said. empty if none")
    why: str = Field(default="", description="the context a team needs, with any numbers said")


class Heard(BaseModel):
    actions: list[Action] = Field(default_factory=list,
                                  description="each new thing that needs doing. empty when nothing")


def said(a: Action) -> str:
    """How an action reads in the room."""
    extra = [x for x in (a.who and f"for {a.who}", a.due and f"by {a.due}") if x]
    return f"action: {a.what}" + (f" ({', '.join(extra)})" if extra else "") + (f". {a.why}" if a.why else "")


class Listener:
    def __init__(self, room: str, me: str, pm: str, model: Model | str | None = None,
                 context: str = ""):
        self.room, self.me, self.pm = room, me, pm
        model = model or os.environ.get("RENGA_MODEL", DEFAULT_MODEL)
        role = ROLES["listener"]
        self.agent = Agent(
            model, output_type=Heard, name="listener", defer_model_check=True,
            instructions=f"{role.instructions()}\n\n## you\n\n{voice(role.personality)}\n\n"
                         "## the meeting\n\nyou've posted what's been said. now pick out what "
                         "needs doing: a request, a decision someone has to act on, a promise, "
                         "a problem to fix. each action goes to the project manager, so write it "
                         "so they can act without having heard the call. actions you've already "
                         "sent are marked; never send the same one twice." + about(context))

    async def run(self, seen: list[str], new: list[str]) -> AsyncIterator[Line]:
        """`seen` is what was said before (context), `new` is what to listen for actions in."""
        prompt = ("earlier in the meeting, already listened to:\n\n" + ("\n".join(seen) or "(nothing)")
                  + "\n\nsaid since you last listened:\n\n" + "\n".join(new))
        yield Line(agent_id=self.me, channel=self.room, kind="thinking", text="")
        for a in (await self.agent.run(prompt)).output.actions:
            yield Line(agent_id=self.me, channel=self.room, kind="task", to=self.pm,
                       text=said(a), data={"action": a.model_dump()})
