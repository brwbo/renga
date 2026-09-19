"""The note-taker's brain: it keeps the meeting's notes. When the meeting
pauses it reads what's new, with the notes it last posted, and posts the
notes again when anything worth keeping was said: a running summary, the
decisions, who owes what, and what's still open.

    meeting lines + the last notes -> note-taker: Notes -> the notes, as a card"""

import os
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from .crew import DEFAULT_MODEL, Line, about
from .personality import voice
from .roles import ROLES


class Notes(BaseModel):
    changed: bool = Field(description="false when nothing new is worth writing down; the notes stay as they are")
    summary: list[str] = Field(default_factory=list, description="a line per topic, in the order they came up")
    decisions: list[str] = Field(default_factory=list, description="each decision, with who made it")
    owed: list[str] = Field(default_factory=list, description="each promise: who, what, by when, as said")
    open: list[str] = Field(default_factory=list, description="questions nobody has answered yet")


def written(n: Notes) -> str:
    """The notes as markdown, for the card in the room."""
    parts = [(title, items) for title, items in (("summary", n.summary), ("decisions", n.decisions),
                                                  ("who owes what", n.owed), ("open", n.open)) if items]
    return "\n\n".join(f"## {t}\n\n" + "\n".join(f"- {i}" for i in items) for t, items in parts)


class NoteTaker:
    def __init__(self, room: str, me: str, model: Model | str | None = None, context: str = ""):
        self.room, self.me = room, me
        model = model or os.environ.get("RENGA_MODEL", DEFAULT_MODEL)
        role = ROLES["note-taker"]
        self.agent = Agent(
            model, output_type=Notes, name="note-taker", defer_model_check=True,
            instructions=f"{role.instructions()}\n\n## you\n\n{voice(role.personality)}\n\n"
                         "## the notes\n\nyou get the notes you last posted and what's been said "
                         "since. write the whole notes again, the old with the new folded in: "
                         "drop nothing that still stands, and move a question to decisions once "
                         "it's settled. when nothing new is worth keeping, say so and change "
                         "nothing." + about(context))

    async def run(self, notes: str, seen: list[str], new: list[str]) -> AsyncIterator[Line]:
        prompt = ("your notes so far:\n\n" + (notes or "(none yet)")
                  + "\n\nearlier in the meeting:\n\n" + ("\n".join(seen) or "(nothing)")
                  + "\n\nsaid since you last wrote:\n\n" + "\n".join(new))
        yield Line(agent_id=self.me, channel=self.room, kind="thinking", text="")
        out = (await self.agent.run(prompt)).output
        if out.changed and (md := written(out)):
            yield Line(agent_id=self.me, channel=self.room, kind="chat", text="the notes so far",
                       data={"deliverable": md, "notes": out.model_dump(exclude={"changed"})})
