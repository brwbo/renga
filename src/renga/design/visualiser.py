"""The visualiser's brain: the meeting's eyes. It wakes when the extension
has looked at the shared tab for it (a screenshot and the page text) and
says what's on screen, and when the meeting pauses, to draw what was just
described (a flow, a timeline, who owns what) as an svg diagram.

    a look at the screen, or meeting lines -> visualiser: Seen -> a line, a diagram"""

import base64
import os
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model

from .crew import DEFAULT_MODEL, File, Line, about
from .personality import voice
from .roles import ROLES


class Screen(BaseModel):
    """One look at the shared tab, as the extension sent it."""

    url: str = ""
    title: str = ""
    text: str = ""
    image: str = ""        # base64
    media_type: str = ""   # image/jpeg or image/png
    because: str = ""      # the words on the call that asked for the look
    slide: int = 0         # which slide of a presentation this is, when someone's presenting


class Seen(BaseModel):
    say: str = Field(default="", description="one or two lines to the room: what's on screen, or what "
                                              "the diagram shows. empty when there's nothing to say")
    notes: str = Field(default="", description="only for a slide: everything on it, in markdown: "
                                                "the title, every line of text, every number and "
                                                "label exactly as shown, and what each chart, table "
                                                "or diagram shows. empty for anything else")
    diagram: File | None = Field(default=None, description="a diagram of what the meeting just described, "
                                                           "as one self-contained svg. none when nothing "
                                                           "said has a shape worth drawing")


class Visualiser:
    def __init__(self, room: str, me: str, model: Model | str | None = None, context: str = ""):
        self.room, self.me = room, me
        model = model or os.environ.get("RENGA_MODEL", DEFAULT_MODEL)
        role = ROLES["visualiser"]
        self.agent = Agent(
            model, output_type=Seen, name="visualiser", defer_model_check=True,
            instructions=f"{role.instructions()}\n\n## you\n\n{voice(role.personality)}\n\n"
                         "## looking\n\nwhen you're given a look at the screen, say what's on it "
                         "in a line or two, with its numbers and labels exactly as shown. when "
                         "you're given only what was said, draw a diagram if, and only if, "
                         "someone described a flow, a sequence, a structure or who owns what; "
                         "otherwise say nothing. a diagram is one svg: a viewBox, boxes and "
                         "arrows, readable text, inline styles, no scripts, no images, no "
                         "outside links. lines from `you` are what you've already posted; "
                         "don't draw the same thing twice.\n\n## a presentation\n\nwhen the look "
                         "is a slide, take in all of it: write everything on it in `notes`, so "
                         "anyone who missed it, and the project manager, has the whole slide. "
                         "`say` is then one line: the slide's number, its title and its point."
                         + about(context))

    async def run(self, seen: list[str], new: list[str], screen: Screen | None = None) -> AsyncIterator[Line]:
        prompt = ("earlier in the meeting:\n\n" + ("\n".join(seen) or "(nothing)")
                  + "\n\nsaid since you last looked:\n\n" + ("\n".join(new) or "(nothing)"))
        parts: list = [prompt]
        if screen:
            look = f"what's on screen now: {screen.title or '(untitled)'} ({screen.url})"
            if screen.slide:
                look += f". someone is presenting: this is slide {screen.slide}"
            if screen.because:
                look += f'. you looked because someone said "{screen.because}"'
            parts.append(look + "\n\nthe page's text:\n\n" + (screen.text or "(none)"))
            if screen.image:
                parts.append(BinaryContent(base64.b64decode(screen.image), media_type=screen.media_type))
        yield Line(agent_id=self.me, channel=self.room, kind="thinking", text="")
        out = (await self.agent.run(parts)).output
        if screen and screen.slide and out.notes:
            yield Line(agent_id=self.me, channel=self.room, kind="chat",
                       text=out.say or f"slide {screen.slide}",
                       data={"slide": screen.slide, "notes": out.notes, "deliverable": out.notes})
        elif out.diagram:
            yield Line(agent_id=self.me, channel=self.room, kind="chat",
                       text=out.say or "a diagram of what was just described",
                       data={"files": [out.diagram.model_dump()]})
        elif out.say:
            yield Line(agent_id=self.me, channel=self.room, kind="chat", text=out.say)
