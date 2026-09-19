"""The visualiser's brain: the meeting's eyes, nothing more. It wakes when
the extension has looked at the screen for it (a screenshot and the page
text: a shared tab, a slide of a presentation, something someone said "as
you can see" about) and writes down everything on it, for the project
manager to brief the design team with. It never makes anything itself.

    a look at the screen -> visualiser: Seen -> a line, and the notes under it"""

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
    say: str = Field(default="", description="one line to the room: what's on screen and its point "
                                              "(for a slide: its number and title)")
    notes: str = Field(default="", description="everything on screen, in markdown: the title, every "
                                                "line of text, every number and label exactly as "
                                                "shown, and what each chart, table or picture shows. "
                                                "only what's there: nothing made up, nothing drafted")


class Visualiser:
    def __init__(self, room: str, me: str, model: Model | str | None = None, context: str = ""):
        self.room, self.me = room, me
        model = model or eyes_model()
        role = ROLES["visualiser"]
        self.agent = Agent(
            model, output_type=Seen, name="visualiser", defer_model_check=True,
            instructions=f"{role.instructions()}\n\n## you\n\n{voice(role.personality)}\n\n"
                         "## looking\n\nyou're given a look at the screen: a screenshot and the "
                         "page's text. write down everything on it in `notes`, with its numbers "
                         "and labels exactly as shown, and say in `say` what it is in a line. "
                         "when someone is presenting, this is one of their slides: take in all of "
                         "it, so the project manager has the whole deck. what was said in the "
                         "meeting is only there to help you read the screen.\n\n## what you "
                         "never do\n\nyou don't make anything: no copy, no posts, no drafts, no "
                         "images, no diagrams, no suggestions. even when someone asks for "
                         "material, that's the design team's work, and the project manager hands "
                         "it to them with what you wrote down." + about(context))

    async def run(self, seen: list[str], new: list[str], screen: Screen | None = None) -> AsyncIterator[Line]:
        """Only a look at the screen gives it anything to do."""
        if not screen:
            return
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
        if not (out.notes or out.say):
            return
        label = f"slide {screen.slide}" if screen.slide else (screen.title or "the screen")
        data = {"notes": out.notes, "deliverable": out.notes, "shown": label}
        if screen.slide:
            data["slide"] = screen.slide
        yield Line(agent_id=self.me, channel=self.room, kind="chat", text=out.say or label, data=data)
