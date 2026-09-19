"""The listener's ears when the call has no captions: one chunk of the call's
audio (a few seconds of wav, recorded by the chrome extension from the meet
tab) in, what was said out, a line per turn, as the listener. It's the same
transcript captions would give, so the project manager reads it the same way.

Gemini hears audio; claude doesn't, so this uses a gemini model whatever the
agents think with (RENGA_EARS_MODEL, flash by default: it's quick and cheap).

    audio chunk + the last few lines -> ears: Heard -> "who: what they said", each"""

import os
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model

from .crew import Line, about

EARS_MODEL = "google:gemini-3.6-flash"


def ears_model() -> str:
    return os.environ.get("RENGA_EARS_MODEL", EARS_MODEL)


class Said(BaseModel):
    who: str = Field(description="who said it: their name if the call makes it clear, "
                                 "otherwise 'speaker 1', 'speaker 2'… kept the same all call")
    text: str = Field(description="what they said, in their own words")


class Heard(BaseModel):
    lines: list[Said] = Field(default_factory=list,
                              description="a line per turn, in order. empty when nobody spoke")


INSTRUCTIONS = """\
# ears

you turn a few seconds of a work call's audio into a transcript: who said
what, a line per turn, in order. you don't summarise, judge or answer.

- keep people's own words. drop only ums, false starts and crosstalk noise.
- keep numbers, dates, names and promises exactly as said.
- you hear only this chunk, so you can't tell voices from earlier ones.
  name a speaker only when this audio makes it clear: they say who they
  are, they're addressed by name, or they carry on the transcript's last
  line mid-sentence. never borrow a name from the transcript on a guess:
  a wrong name is worse than 'speaker 1', 'speaker 2' and so on.
- the audio is cut every few seconds: a sentence may start before it or run
  past it. write what you hear; don't finish other people's sentences.
- music, silence, typing, hold tones: not speech, leave them out. when
  nobody speaks, return no lines."""


class Ears:
    def __init__(self, room: str, me: str, model: Model | str | None = None, context: str = ""):
        self.room, self.me = room, me
        self.agent = Agent(model or ears_model(), output_type=Heard, name="ears",
                           defer_model_check=True, instructions=INSTRUCTIONS + about(context))

    async def run(self, audio: bytes, mime: str, recent: list[str]) -> AsyncIterator[Line]:
        """`recent` is the transcript so far, for who's who and where a cut sentence began."""
        prompt = ("the transcript so far:\n\n" + ("\n".join(recent) or "(the call just started)")
                  + "\n\nwhat's said next is in this audio:")
        heard = (await self.agent.run([prompt, BinaryContent(data=audio, media_type=mime)])).output
        for s in heard.lines:
            if s.text.strip():
                yield Line(agent_id=self.me, channel=self.room, kind="chat",
                           text=f"{s.who.strip() or 'someone'}: {s.text.strip()}")
