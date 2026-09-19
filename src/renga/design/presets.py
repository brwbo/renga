"""The seven ready-made design teams from designteam (github.com/pablostanley/
designteam-app, mit). Each one is a room in renga with a lead, and each runs
in its own modal sandbox (sandbox.py)."""

from typing import get_args

from pydantic import BaseModel, Field, model_validator

from .personality import Character, Trait
from .roles import ROLES, DesignRoleId, Role, RoleId


class Member(BaseModel):
    role: RoleId
    traits: list[Trait] = Field(default_factory=list)

    def character(self) -> Character:
        return Character(personality=ROLES[self.role].personality, traits=self.traits)


class Preset(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    does: str
    members: list[Member] = Field(min_length=1)
    lead_role: RoleId | None = None  # when the lead isn't worked out from the members

    @model_validator(mode="after")
    def _one_of_each(self) -> "Preset":
        roles = [m.role for m in self.members]
        if len(set(roles)) != len(roles):
            raise ValueError(f"{self.id} hires the same role twice")
        if self.lead_role and self.lead_role not in roles:
            raise ValueError(f"{self.id}'s lead isn't one of its members")
        for m in self.members:
            m.character()  # checks the traits
        return self

    @property
    def lead(self) -> RoleId:
        """The creative director when there is one, then whoever is a leader,
        then whoever is listed first."""
        if self.lead_role:
            return self.lead_role
        roles = [m.role for m in self.members]
        if "creative-director" in roles:
            return "creative-director"
        return next((m.role for m in self.members if "leader" in m.traits), roles[0])

    def member(self, role: str) -> Member | None:
        return next((m for m in self.members if m.role == role), None)

    def roles(self) -> list[Role]:
        return [ROLES[m.role] for m in self.members]


def _team(id: str, does: str, *members: tuple[str, list[str]]) -> Preset:
    return Preset(id=id, does=does,
                  members=[Member(role=r, traits=t) for r, t in members])


PRESETS: list[Preset] = [
    Preset(id="full-studio", does="the whole crew, all sixteen specialists",
           members=[Member(role=r) for r in get_args(DesignRoleId)]),
    _team("landing-page-sprint", "ships a landing page that converts, fast",
          ("researcher", ["methodical", "detail-obsessed", "introvert", "thinking"]),
          ("copywriter", ["sassy", "fast-shipper", "extrovert", "feeling"]),
          ("graphic-designer", ["intense", "perfectionist", "independent", "perceiving"]),
          ("ux-designer", ["chill", "iterative", "collaborator", "judging"])),
    _team("brand-campaign", "a campaign that hangs together across every channel",
          ("copywriter", ["provocative", "chaotic-creative", "independent", "feeling"]),
          ("graphic-designer", ["stoic", "perfectionist", "introvert", "thinking"]),
          ("social-media-designer", ["enthusiastic", "fast-shipper", "extrovert", "optimist"]),
          ("creative-director", ["intense", "big-picture", "leader", "judging"])),
    _team("content-machine", "polished content, lots of it",
          ("copywriter", ["enthusiastic", "fast-shipper", "collaborator", "feeling"]),
          ("editorial-designer", ["deadpan", "perfectionist", "introvert", "judging"]),
          ("social-media-designer", ["sassy", "chaotic-creative", "extrovert", "risk-taker"]),
          ("ux-writer", ["nurturing", "methodical", "mentor", "thinking"])),
    _team("product-team", "product experiences built around the people using them",
          ("ux-designer", ["chill", "iterative", "collaborator", "feeling"]),
          ("ux-writer", ["nurturing", "detail-obsessed", "supporter", "thinking"]),
          ("graphic-designer", ["intense", "perfectionist", "challenger", "perceiving"]),
          ("researcher", ["stoic", "methodical", "independent", "realist"])),
    _team("full-stack-design", "brand strategy all the way to production code",
          ("design-engineer", ["deadpan", "fast-shipper", "independent", "thinking"]),
          ("ux-designer", ["chill", "iterative", "collaborator", "feeling"]),
          ("graphic-designer", ["intense", "perfectionist", "challenger", "perceiving"]),
          ("brand-strategist", ["stoic", "big-picture", "leader", "cautious"]),
          ("content-strategist", ["nurturing", "methodical", "mentor", "judging"])),
    _team("marketing-blitz", "campaigns that convert on every channel",
          ("marketing-strategist", ["intense", "big-picture", "leader", "thinking"]),
          ("copywriter", ["sassy", "fast-shipper", "extrovert", "risk-taker"]),
          ("social-media-designer", ["enthusiastic", "chaotic-creative", "collaborator", "optimist"]),
          ("seo-specialist", ["deadpan", "detail-obsessed", "introvert", "realist"]),
          ("graphic-designer", ["stoic", "perfectionist", "independent", "cautious"])),
]

PRESETS_BY_ID: dict[str, Preset] = {p.id: p for p in PRESETS}


def agent_id(preset: str, role: str) -> str:
    """The agent's id in renga: one per role per team room."""
    return f"{preset}-{role}"
