"""The visualiser's brain: the meeting's eyes, nothing more. It wakes when
the extension has looked at the screen for it (a slide while someone
presents, or a tab you asked it to read) and writes down, a short line
each, only what the team could use from it, into a context doc the project
manager briefs the design team from. The chat only hears that it's reading
and, at the end, gets the doc. It never makes anything itself.

    a look at the screen -> visualiser: Seen -> a line per finding, into the doc"""

import base64
import os
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model

from .crew import DEFAULT_MODEL, Line, about
from .personality import voice
from .roles import ROLES

# Slides come every few seconds, so looking uses flash whenever the agents
# think with gemini: its key is the one in the sandbox. RENGA_EYES_MODEL
# picks another.
EYES_MODEL = "google:gemini-3.6-flash"


def eyes_model() -> str:
    if chosen := os.environ.get("RENGA_EYES_MODEL"):
        return chosen
    thinks = os.environ.get("RENGA_MODEL", DEFAULT_MODEL)
    return EYES_MODEL if thinks.startswith("google:") else thinks


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
    found: list[str] = Field(default_factory=list, description=(
        "what the slide gives the team to use in what they're making, one short line each, like "
        "a text message: a fact, a number with what it measures, a name, a claim, a before and "
        "after, what a chart shows. exact numbers and wording. never the call itself (buttons, "
        "microphone or camera state, video tiles, names under video, 'you are presenting', the "
        "meet or browser ui), never what the slide looks like. empty when there's nothing worth "
        "using"))


class Visualiser:
    def __init__(self, room: str, me: str, model: Model | str | None = None, context: str = ""):
        self.room, self.me = room, me
        model = model or eyes_model()
        role = ROLES["visualiser"]
        self.agent = Agent(
            model, output_type=Seen, name="visualiser", defer_model_check=True,
            instructions=f"{role.instructions()}\n\n## you\n\n{voice(role.personality)}\n\n"
                         "## looking\n\nyou're given a screenshot of the meeting while someone "
                         "presents. read the slide and pull out only what the team could use in "
                         "what they're making: facts, numbers, names, claims, comparisons. ignore "
                         "the call around it: meet's buttons, mic and camera, video tiles, names, "
                         "toolbars, the browser. a short, exact line per finding. if the slide has "
                         "nothing useful, or you only see the call, find nothing. what was said "
                         "in the meeting is only there to help you read the slide.\n\n## what you "
                         "never do\n\nyou don't make anything: no copy, no posts, no drafts, no "
                         "images, no diagrams, no suggestions. even when someone asks for "
                         "material, that's the design team's work, and the project manager hands "
                         "it to them with what you wrote down." + about(context))

    async def run(self, seen: list[str], new: list[str], screen: Screen | None = None) -> AsyncIterator[Line]:
        """Only a look at the screen gives it anything to do."""
        if not screen or (screen.because and not screen.slide):
            return  # someone saying "as you can see" isn't a presentation
        look = f"what's on screen now: {screen.title or '(untitled)'} ({screen.url})"
        if screen.slide:
            look += f". someone is presenting: this is slide {screen.slide}"
        if screen.because:
            look += f'. you looked because someone said "{screen.because}"'
        parts: list = [("what was said in the meeting, for context:\n\n" + ("\n".join([*seen, *new][-30:])
                        or "(nothing)")), look + "\n\nthe page's text:\n\n" + (screen.text or "(none)")]
        if screen.image:
            parts.append(BinaryContent(base64.b64decode(screen.image), media_type=screen.media_type))
        yield Line(agent_id=self.me, channel=self.room, kind="thinking", text="")
        out = (await self.agent.run(parts)).output
        found = [f.strip().lstrip("-• ").strip() for f in out.found]
        notes = "\n".join(f"- {f}" for f in found if f)
        if screen.slide:
            # A slide's notes stay out of the chat, and are posted even when
            # empty: when the presentation ends they all go into one notes
            # file, which waits until every slide has been read.
            yield Line(agent_id=self.me, channel=self.room, kind="chat",
                       text=notes or "nothing worth using on this slide",
                       data={"notes": notes, "shown": f"slide {screen.slide}", "slide": screen.slide,
                             "quiet": True})
        elif notes:  # a tab you asked it to read: what it found goes in a doc, not the chat
            shown = screen.title or "the screen"
            yield Line(agent_id=self.me, channel=self.room, kind="chat",
                       text="read the tab and wrote it up in a context doc.",
                       data={"notes": notes, "shown": shown,
                             "files": [{"name": "tab-context.md", "content": f"# context from {shown}\n\n{notes}\n"}]})
