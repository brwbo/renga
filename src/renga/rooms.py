"""A new room in a team, from the team page: a name and what it's for. It
starts empty; agents join it with "+ add agent", as in any room. Stored
like a workflow's rooms (teams.py), so built-in teams can have them too."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from . import agents
from .bus import emit
from .teams import slug
from .teams import store as teams

router = APIRouter()


class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    purpose: str = Field(default="", max_length=200)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = slug(v.strip().lstrip("#"))
        if not v:
            raise ValueError("needs at least one letter or number")
        return v


@router.post("/api/teams/{team_id}/rooms", status_code=201)
async def add_room(team_id: str, body: RoomIn) -> agents.Room:
    team = agents.team(team_id)
    if not team:
        raise HTTPException(404, f"no team called {team_id!r}")
    if any(r.name == body.name for r in agents.all_rooms(team_id)):
        raise HTTPException(409, f"{team.name} already has a #{body.name}")
    room = agents.Room(id=f"{team_id}-{body.name}", team=team_id, name=body.name,
                       purpose=body.purpose.strip())
    try:
        teams.add_rooms([room], [], taken_rooms={r.id for r in agents.all_rooms()},
                        taken_agents=set())
    except ValueError as err:
        raise HTTPException(409, f"#{body.name} is taken, try another name") from err
    await emit(room.id, "state", from_="admin", text=f"#{room.name} is set up")
    return room
