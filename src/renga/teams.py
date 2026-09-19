"""Teams made from the teams page, and agents and rooms added to any team
later. Each team is a row holding the team, its rooms and the agents it
started with, so a team is written in one go and never half made. The
built-in teams in agents.py are not stored here, but agents and rooms added
to them are. A workflow's rooms and their agents are also written in one go.
Every team, built in or not, can have a context: a markdown doc (a
design.md, a brand guide, the audience) every agent in the team reads."""

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from .agents import STARTERS, Agent, Room, Sense, Team, from_library
from .db import DB_PATH
from .design.roles import ROLES, RoleId

_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    created_ts INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS removed (
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    PRIMARY KEY (kind, id)
);
CREATE TABLE IF NOT EXISTS added_agents (
    id TEXT PRIMARY KEY,
    created_ts INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS added_rooms (
    id TEXT PRIMARY KEY,
    created_ts INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS context (
    team TEXT PRIMARY KEY,
    updated_ts INTEGER NOT NULL,
    text TEXT NOT NULL
);
"""

REPO = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    repo: str = Field(max_length=140)
    purpose: str = Field(default="", max_length=200)
    rooms: list[str] = Field(default_factory=lambda: ["general"], min_length=1, max_length=8)
    senses: list[Sense] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip().lower()
        if not slug(v):
            raise ValueError("needs at least one letter or number")
        return v

    @field_validator("repo")
    @classmethod
    def _repo(cls, v: str) -> str:
        v = v.strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
        if not REPO.match(v):
            raise ValueError("should look like owner/name")
        return v

    @field_validator("rooms")
    @classmethod
    def _rooms(cls, v: list[str]) -> list[str]:
        names = [n.strip().lower().lstrip("#") for n in v if slug(n)]
        if not names:
            raise ValueError("needs at least one room")
        if len({slug(n) for n in names}) != len(names):
            raise ValueError("two rooms have the same name")
        return names


class AgentIn(BaseModel):
    """A new agent: either from the library (`template`, with an optional
    name), or made up (a `name` and a `role`)."""

    name: str | None = Field(default=None, min_length=1, max_length=24)
    role: str | None = Field(default=None, min_length=1, max_length=200)
    senses: list[Sense] = Field(default_factory=list)
    template: RoleId | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not slug(v):
            raise ValueError("needs at least one letter or number")
        return v

    @model_validator(mode="after")
    def _either(self) -> "AgentIn":
        if not self.template and not (self.name and self.role):
            raise ValueError("pick an agent from the library, or give a name and a role")
        return self


class TeamStore:
    def __init__(self, path: Path = DB_PATH):
        self._path = path
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, check_same_thread=False)

    def all(self) -> list[tuple[Team, list[Room], list[Agent]]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM teams ORDER BY created_ts").fetchall()
        out = []
        for (data,) in rows:
            d = json.loads(data)
            out.append((Team(**d["team"]), [Room(**r) for r in d["rooms"]],
                        [Agent(**a) for a in d["agents"]]))
        return out

    def create(self, body: TeamIn, taken_teams: set[str], taken_rooms: set[str],
               taken_agents: set[str]) -> tuple[Team, list[Room], list[Agent]]:
        """Build the team from the form and store it. Raises ValueError when
        the team, or any room or agent id it would make, already exists."""
        team_id = slug(body.name)
        team = Team(id=team_id, name=body.name, repo=body.repo,
                    purpose=body.purpose.strip() or f"works on {body.repo}")
        rooms = [Room(id=f"{team_id}-{slug(n)}", team=team_id, name=slug(n),
                      purpose="the whole team, until it needs more rooms" if i == 0 else "")
                 for i, n in enumerate(body.rooms)]
        agents = [Agent(id=f"{team_id}-{STARTERS[s]['name']}", room=rooms[0].id, senses=[s],
                        **STARTERS[s]) for s in dict.fromkeys(body.senses)]
        with self._lock:
            if team_id in taken_teams:
                raise ValueError(f"there's already a team called {body.name!r}")
            clash = {r.id for r in rooms} & taken_rooms or {a.id for a in agents} & taken_agents
            if clash:
                raise ValueError(f"{sorted(clash)[0]!r} is already taken, try another name")
            data = {"team": team.model_dump(), "rooms": [r.model_dump() for r in rooms],
                    "agents": [a.model_dump() for a in agents]}
            with self._connect() as conn:
                conn.execute("INSERT INTO teams (id, created_ts, data) VALUES (?, ?, ?)",
                             (team_id, int(time.time() * 1000), json.dumps(data)))
        return team, rooms, agents

    def added(self) -> list[Agent]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM added_agents ORDER BY created_ts").fetchall()
        return [Agent(**json.loads(data)) for (data,) in rows]

    def add_agent(self, body: AgentIn, room: Room, taken: set[str]) -> Agent:
        """An agent joining a room. Its id is the team's plus its name, so two
        teams can each have a `researcher`. Raises ValueError on a clash."""
        if body.template:
            name = slug(body.name or ROLES[body.template].name)
            agent = from_library(body.template, f"{room.team}-{name}", room.id,
                                 name=body.name or ROLES[body.template].name)
        else:
            name = slug(body.name)
            agent = Agent(id=f"{room.team}-{name}", name=body.name, role=body.role.strip(),
                          room=room.id, initials=name.replace("-", "")[:2] or name[:2],
                          senses=list(dict.fromkeys(body.senses)))
        with self._lock:
            if agent.id in taken:
                raise ValueError(f"there's already an agent called {body.name!r} in this team")
            with self._connect() as conn:
                conn.execute("INSERT INTO added_agents (id, created_ts, data) VALUES (?, ?, ?)",
                             (agent.id, int(time.time() * 1000), json.dumps(agent.model_dump())))
        return agent

    def added_rooms(self) -> list[Room]:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM added_rooms ORDER BY created_ts").fetchall()
        return [Room(**json.loads(data)) for (data,) in rows]

    def add_rooms(self, rooms: list[Room], agents: list[Agent],
                  taken_rooms: set[str], taken_agents: set[str]) -> None:
        """Rooms and the agents in them, all or nothing. Raises ValueError
        when any id is already taken."""
        now = int(time.time() * 1000)
        with self._lock:
            clash = {r.id for r in rooms} & taken_rooms or {a.id for a in agents} & taken_agents
            if clash:
                raise ValueError(f"{sorted(clash)[0]!r} is already taken in this team")
            with self._connect() as conn:
                conn.executemany("INSERT INTO added_rooms (id, created_ts, data) VALUES (?, ?, ?)",
                                 [(r.id, now, json.dumps(r.model_dump())) for r in rooms])
                conn.executemany("INSERT INTO added_agents (id, created_ts, data) VALUES (?, ?, ?)",
                                 [(a.id, now, json.dumps(a.model_dump())) for a in agents])

    # ---- the team's context -----------------------------------------------
    def context(self, team_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT text FROM context WHERE team = ?", (team_id,)).fetchone()
        return row[0] if row else ""

    def set_context(self, team_id: str, text: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO context (team, updated_ts, text) VALUES (?, ?, ?) "
                         "ON CONFLICT(team) DO UPDATE SET updated_ts = excluded.updated_ts, "
                         "text = excluded.text", (team_id, int(time.time() * 1000), text))

    # ---- deleting ---------------------------------------------------------
    # A team or agent made here is deleted outright. A built-in one lives in
    # the code, so it's written down as removed and the lookups hide it. The
    # event log keeps everything that was said either way.
    def removed(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {"team": set(), "agent": set()}
        with self._connect() as conn:
            for kind, id_ in conn.execute("SELECT kind, id FROM removed"):
                out.setdefault(kind, set()).add(id_)
        return out

    def delete_team(self, team_id: str, room_ids: set[str]) -> None:
        with self._lock, self._connect() as conn:
            gone = conn.execute("DELETE FROM teams WHERE id = ?", (team_id,)).rowcount
            if not gone:
                conn.execute("INSERT OR IGNORE INTO removed (kind, id) VALUES ('team', ?)", (team_id,))
            conn.execute("DELETE FROM context WHERE team = ?", (team_id,))
            conn.executemany("DELETE FROM added_rooms WHERE id = ?", [(r,) for r in room_ids])
            for (id_, data) in conn.execute("SELECT id, data FROM added_agents").fetchall():
                if json.loads(data)["room"] in room_ids:
                    conn.execute("DELETE FROM added_agents WHERE id = ?", (id_,))

    def delete_agent(self, agent_id: str) -> None:
        with self._lock, self._connect() as conn:
            if conn.execute("DELETE FROM added_agents WHERE id = ?", (agent_id,)).rowcount:
                return
            for (tid, data) in conn.execute("SELECT id, data FROM teams").fetchall():
                d = json.loads(data)
                kept = [a for a in d["agents"] if a["id"] != agent_id]
                if len(kept) != len(d["agents"]):
                    d["agents"] = kept
                    conn.execute("UPDATE teams SET data = ? WHERE id = ?", (json.dumps(d), tid))
                    return
            conn.execute("INSERT OR IGNORE INTO removed (kind, id) VALUES ('agent', ?)", (agent_id,))


store = TeamStore()
