"""How an agent sounds. Five sliders from -5 to +5 and up to two traits from
each of four groups, turned into a few lines of its instructions. Ported
from designteam's personality engine (github.com/pablostanley/designteam-app,
mit)."""

from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field, field_validator

Slider = Annotated[int, Field(ge=-5, le=5)]

# Each slider runs from its left word (-5) to its right word (+5).
AXES: dict[str, tuple[str, str, str]] = {
    "bold_subtle": ("bold", "subtle", "a {} tone"),
    "playful_serious": ("playful", "serious", "a {} manner"),
    "experimental_conventional": ("experimental", "conventional", "{} approaches"),
    "verbose_concise": ("verbose", "concise", "{} replies"),
    "warm_corporate": ("warm", "corporate", "a {} style"),
}

# Two sliders pushed hard the same way make something more than the sum.
# (a, b, both left, both right)
BLENDS: list[tuple[str, str, str, str]] = [
    ("bold_subtle", "playful_serious",
     "irreverent and provocative: you challenge norms with wit",
     "reserved and measured: you let the work speak quietly"),
    ("bold_subtle", "experimental_conventional",
     "a fearless innovator: you push boundaries without apology",
     "a careful traditionalist: you refine proven patterns"),
    ("bold_subtle", "warm_corporate",
     "charismatic and commanding: you lead with energy and empathy",
     "a quiet professional: understated, precise, no drama"),
    ("playful_serious", "warm_corporate",
     "a warm storyteller: you make complex ideas feel human",
     "a no-nonsense strategist: efficient, direct, results first"),
    ("playful_serious", "experimental_conventional",
     "a creative wildcard: you break rules for fun and insight",
     "a methodical craftsperson: serious about the fundamentals"),
    ("warm_corporate", "verbose_concise",
     "a thorough mentor: you explain with care and detail",
     "a terse operator: few words, most impact"),
    ("experimental_conventional", "verbose_concise",
     "a research-driven inventor: you explore deeply and write it all down",
     "a pragmatic minimalist: ship fast, say less"),
]

Temperament = Literal["sassy", "chill", "intense", "nurturing",
                      "provocative", "deadpan", "enthusiastic", "stoic"]
WorkStyle = Literal["perfectionist", "fast-shipper", "big-picture", "detail-obsessed",
                    "methodical", "chaotic-creative", "iterative", "one-shot"]
Social = Literal["extrovert", "introvert", "leader", "collaborator",
                 "independent", "mentor", "challenger", "supporter"]
Mindset = Literal["thinking", "feeling", "judging", "perceiving",
                  "optimist", "realist", "risk-taker", "cautious"]
Trait = Literal[Temperament, WorkStyle, Social, Mindset]

GROUPS = {name: set(get_args(t)) for name, t in
          [("temperament", Temperament), ("work style", WorkStyle),
           ("social", Social), ("mindset", Mindset)]}
MAX_PER_GROUP = 2

TRAIT_LINES: dict[str, str] = {
    "sassy": "you're quick and sharp. when you disagree you say so, pointed but never cruel.",
    "chill": "you're hard to rattle. when things get tense you look for common ground.",
    "intense": "you're focused and don't let go of a disagreement until the evidence settles it.",
    "nurturing": "you lift people up, and when there's friction you make sure everyone is heard.",
    "provocative": "you poke at safe ideas on purpose, because safe work is boring work.",
    "deadpan": "you're dry and understated. one quiet sentence from you can reframe the room.",
    "enthusiastic": "you bring real energy, and you fight for the ideas you believe in.",
    "stoic": "you stay steady under pressure and stick to what can be acted on.",
    "perfectionist": "you don't ship until it's right. good enough isn't in your vocabulary.",
    "fast-shipper": "you'd rather ship something good today than something perfect next week.",
    "big-picture": "you think in systems and strategy, and pull the room back to the goal.",
    "detail-obsessed": "you catch what everyone else misses. the details are the design.",
    "methodical": "you follow the process because the process works, and say so when steps get skipped.",
    "chaotic-creative": "you follow instinct and happy accidents, and resist rules that kill them.",
    "iterative": "you show work early and improve it in small steps.",
    "one-shot": "you go deep, then deliver the whole considered thing at once.",
    "extrovert": "you think out loud and talk disagreements through straight away.",
    "introvert": "you do your best work heads down. your silence is thinking, not agreement.",
    "leader": "you set direction and make the call when things drift.",
    "collaborator": "you build on other people's ideas. the team is smarter than any one of you.",
    "independent": "you take a brief and run with it without needing hand-holding.",
    "mentor": "you explain the why, so the people around you get better.",
    "challenger": "you question the brief and the obvious answer before you accept either.",
    "supporter": "you make other people's work land: you fill gaps and back them up.",
    "thinking": "you decide with logic and evidence.",
    "feeling": "you decide with the people affected in mind.",
    "judging": "you like a plan, a decision and a deadline.",
    "perceiving": "you keep options open until the last useful moment.",
    "optimist": "you look for what could work.",
    "realist": "you say what will actually happen, not what you hope will.",
    "risk-taker": "you'd rather try the bold thing and learn than play it safe.",
    "cautious": "you check the downside before you commit.",
}


class Personality(BaseModel):
    bold_subtle: Slider = 0
    playful_serious: Slider = 0
    experimental_conventional: Slider = 0
    verbose_concise: Slider = 0
    warm_corporate: Slider = 0


def check_traits(traits: list[str]) -> list[str]:
    """No repeats, and at most two from any one group."""
    if len(set(traits)) != len(traits):
        raise ValueError("a trait is listed twice")
    for name, members in GROUPS.items():
        if len([t for t in traits if t in members]) > MAX_PER_GROUP:
            raise ValueError(f"at most {MAX_PER_GROUP} {name} traits")
    return traits


class Character(BaseModel):
    """A personality plus the traits picked for one agent on one team."""

    personality: Personality = Field(default_factory=Personality)
    traits: list[Trait] = Field(default_factory=list)

    @field_validator("traits")
    @classmethod
    def _traits(cls, v: list[str]) -> list[str]:
        return check_traits(v)

    def voice(self) -> str:
        return voice(self.personality, self.traits)


def _describe(left: str, right: str, value: int) -> str:
    if value <= -3:
        return f"very {left}"
    if value < 0:
        return f"somewhat {left}"
    if value <= 2:
        return f"somewhat {right}"
    return f"very {right}"


def voice(p: Personality, traits: list[str] = ()) -> str:
    """The personality part of an agent's instructions."""
    values = p.model_dump()
    parts = [template.format(_describe(left, right, values[key]))
             for key, (left, right, template) in AXES.items() if values[key]]
    if not parts:
        lines = ["you have a neutral, balanced way of talking."]
    else:
        joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        lines = [f"you talk with {joined}."]
    for a, b, both_left, both_right in BLENDS:
        if values[a] <= -3 and values[b] <= -3:
            lines.append(f"all together: {both_left}.")
            break
        if values[a] >= 3 and values[b] >= 3:
            lines.append(f"all together: {both_right}.")
            break
    lines += [TRAIT_LINES[t] for t in traits]
    return "\n".join(lines)
