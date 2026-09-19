"""Who is in the room. Each agent is a card: a name, a role, and a sprite spec
for the pixel-art generator in web/sprites/sprites.js (carried over from
agentville, where every job wears its job).

The seed roster is the meeting copilot crew. The brains (pydantic ai agents
on modal) are not wired yet; for now a card is a face and a name in the chat."""

from typing import Literal

from pydantic import BaseModel, Field

Work = Literal["typing", "reading", "mining", "writing", "phone", "inspect", "counting"]
Outfit = Literal["suit", "hoodie", "apron", "labcoat", "hivis", "visor", "turtle", "coverall"]
Hat = Literal["none", "beret", "hardhat", "eyeshade", "cap"]


class Sprite(BaseModel):
    skin: int = Field(ge=0, le=4)
    hair: Literal["black", "brown", "blonde", "ginger", "grey", "auburn"]
    style: Literal["parted", "buzz", "long", "bob", "curly", "bun", "bald"]
    accent: Literal["red", "blue", "green", "gold", "purple", "pink", "teal"]
    eyes: Literal["blue", "brown", "green", "hazel", "grey"]
    tie: Literal["tie", "bowtie"] = "tie"
    face: Literal["none", "glasses", "shades", "tache", "beard"] = "none"
    extra: Literal["none", "headset", "coffee", "briefcase", "lanyard"] = "none"
    outfit: Outfit = "hoodie"
    hat: Hat = "none"
    work: Work = "typing"


class Agent(BaseModel):
    id: str
    name: str
    role: str
    lead: bool = False  # the pm: the one agent a person talks to first
    sprite: Sprite


ROSTER: list[Agent] = [
    Agent(id="pm", name="pm", role="runs the room: splits the work, hands it out, reports back",
          lead=True,
          sprite=Sprite(skin=1, hair="black", style="parted", accent="red", eyes="brown",
                        outfit="suit", work="phone")),
    Agent(id="transcript", name="transcript", role="live speech to text, with speaker labels",
          sprite=Sprite(skin=3, hair="black", style="buzz", accent="blue", eyes="brown",
                        extra="headset", work="typing")),
    Agent(id="visual", name="visual", role="reads screen shares and slides",
          sprite=Sprite(skin=0, hair="ginger", style="bob", accent="teal", eyes="green",
                        face="glasses", outfit="labcoat", work="inspect")),
    Agent(id="notes", name="notes", role="running summary, decisions and action items",
          sprite=Sprite(skin=2, hair="brown", style="bun", accent="green", eyes="hazel",
                        outfit="visor", hat="eyeshade", work="writing")),
    Agent(id="actions", name="actions", role="starts on action items and leaves drafts",
          sprite=Sprite(skin=4, hair="black", style="curly", accent="gold", eyes="brown",
                        extra="coffee", outfit="coverall", hat="cap", work="counting")),
    Agent(id="marketing", name="marketing", role="video scripts, posts, blogs and ad copy",
          sprite=Sprite(skin=1, hair="blonde", style="long", accent="pink", eyes="blue",
                        tie="bowtie", extra="lanyard", outfit="apron", hat="beret", work="reading")),
]

BY_ID = {a.id: a for a in ROSTER}
