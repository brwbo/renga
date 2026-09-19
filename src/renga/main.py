"""The server: the event log over http and a websocket, the teams (one per
repo) and their rooms, delegation between rooms, the question queue, and the
agent library with its premade workflows. Serves the chat app in web/ at /.

With RENGA_BRAINS=modal the server also starts the agents' host
(design/sandbox.py listen) in the background, so library agents work
without a second process."""

import base64
import binascii
import contextlib
import io
import json
import os
import re
import uuid
import zipfile
from pathlib import Path

import logfire
from logfire.propagate import get_context
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agents
from .bus import bus, emit
from .cues import cue, looks
from . import hearing
from .rooms import router as new_rooms
from .db import store
from .questions import QuestionIn
from .questions import store as questions
from .teams import AgentIn, TeamIn
from .teams import slug as teams_slug
from .teams import store as teams
from .thinking import thinking
from .workflows import WORKFLOWS, WORKFLOWS_BY_ID

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
EXTENSION = ROOT / "extension"
# Screenshots the extension sends in. Kept as files, never in the event log.
FRAMES = Path(os.environ.get("RENGA_FRAMES", ROOT / "frames"))
FRAMES.mkdir(parents=True, exist_ok=True)
# What the agents make (svg, html, markdown), kept as files like the frames.
FILES = Path(os.environ.get("RENGA_FILES", ROOT / "files"))
FILES.mkdir(parents=True, exist_ok=True)
FILE_TYPES = {"svg": "image/svg+xml", "html": "text/html", "md": "text/markdown",
              "txt": "text/plain", "csv": "text/csv", "json": "application/json", "css": "text/css"}

logfire.configure(send_to_logfire="if-token-present", console=False)

@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("RENGA_BRAINS") == "modal":
        import threading

        from .design.sandbox import listen
        url = os.environ.get("RENGA_URL", "http://localhost:8020")
        threading.Thread(target=listen, args=(url,), daemon=True).start()
    yield


app = FastAPI(title="renga", lifespan=lifespan)
app.include_router(hearing.router)  # the call's audio, when there are no captions
app.include_router(new_rooms)  # a new room in a team, from the team page


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    channel: str = "main"


class SayIn(BaseModel):
    """An agent speaking in the room. The agents on modal post through this."""

    agent_id: str
    text: str = Field(min_length=1, max_length=8000)
    kind: str = "chat"
    to: str | None = None
    data: dict | None = None
    channel: str = "main"


class AnswerIn(BaseModel):
    value: str = Field(min_length=1, max_length=4000)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/agents")
def list_agents() -> list[agents.Agent]:
    return agents.all_agents()


@app.get("/api/teams")
def list_teams() -> list[agents.Team]:
    return agents.all_teams()


@app.post("/api/teams", status_code=201)
def create_team(body: TeamIn) -> dict:
    try:
        team, rooms, members = teams.create(
            body,
            taken_teams={t.id for t in agents.all_teams()},
            taken_rooms={r.id for r in agents.all_rooms()},
            taken_agents={a.id for a in agents.all_agents()},
        )
    except ValueError as err:
        raise HTTPException(409, str(err)) from err
    return {"team": team, "rooms": rooms, "agents": members}


class ContextIn(BaseModel):
    """The team's context: markdown every agent in the team reads."""

    text: str = Field(max_length=50_000)


@app.get("/api/teams/{team_id}/context")
def get_context_doc(team_id: str) -> dict:
    if not agents.team(team_id):
        raise HTTPException(404, f"no team called {team_id!r}")
    return {"team": team_id, "text": teams.context(team_id)}


@app.put("/api/teams/{team_id}/context")
def set_context_doc(team_id: str, body: ContextIn) -> dict:
    if not agents.team(team_id):
        raise HTTPException(404, f"no team called {team_id!r}")
    teams.set_context(team_id, body.text.strip())
    return {"team": team_id, "text": teams.context(team_id)}


@app.get("/api/rooms")
def list_rooms(team: str | None = None) -> list[agents.Room]:
    return agents.all_rooms(team)


@app.post("/api/rooms/{room_id}/agents", status_code=201)
async def add_agent(room_id: str, body: AgentIn) -> agents.Agent:
    room = agents.room(room_id)
    if not room:
        raise HTTPException(404, f"no room called {room_id!r}")
    # Taken: every id, and every name already used anywhere in this team.
    team_rooms = {r.id for r in agents.all_rooms(room.team)}
    everyone = agents.all_agents()
    taken = {a.id for a in everyone} | {f"{room.team}-{teams_slug(a.name)}"
                                         for a in everyone if a.room in team_rooms}
    try:
        agent = teams.add_agent(body, room, taken)
    except ValueError as err:
        raise HTTPException(409, str(err)) from err
    await emit(room.id, "agent_joined", from_=agent.id, text=f"joined #{room.name}")
    return agent


@app.delete("/api/teams/{team_id}", status_code=204)
def delete_team(team_id: str) -> None:
    if not agents.team(team_id):
        raise HTTPException(404, f"no team called {team_id!r}")
    teams.delete_team(team_id, {r.id for r in agents.all_rooms(team_id)})


@app.delete("/api/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: str) -> None:
    who = agents.agent(agent_id)
    if not who:
        raise HTTPException(404, f"no agent called {agent_id!r}")
    teams.delete_agent(agent_id)
    await emit(who.room, "agent_left", from_=who.id, text=f"was removed from #{agents.room(who.room).name}",
               data={"name": who.name})  # it's gone from the roster, so the chat can't look it up


class DelegateIn(BaseModel):
    """A room's lead handing a piece of work to another room in its team:
    the built-in pm, or a project manager from the library."""

    room: str
    text: str = Field(min_length=1, max_length=8000)
    data: dict | None = None
    from_agent: str = "pm"


@app.post("/api/delegate", status_code=201)
async def delegate(body: DelegateIn) -> dict:
    who = agents.agent(body.from_agent)
    if not who:
        raise HTTPException(409, f"there's no {body.from_agent} to delegate the work")
    home = agents.room(who.room)
    if home.lead != who.id:
        raise HTTPException(403, f"only #{home.name}'s lead hands work out")
    room = agents.room(body.room)
    if not room or not room.lead or room.id == home.id or room.team != home.team:
        raise HTTPException(404, f"no room called {body.room!r} to delegate to")
    # One line in the lead's room so you can see where the work went, and
    # the brief itself in the other room, addressed to its lead. The hand-off
    # starts a trace; the brief carries it, so the room's run joins it.
    with logfire.span("{lead} delegates to #{room}", lead=who.id, room=room.id) as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        await emit(home.id, "handoff", from_=who.id, to=f"room:{room.id}",
                   text=f"sent to #{room.name}: {body.text}", data={"room": room.id})
        task = await emit(room.id, "task", from_=who.id, to=room.lead, text=body.text,
                          data={**(body.data or {}), "delegated_from": home.id,
                                "traceparent": get_context().get("traceparent", "")})
        watch = agents.logfire_id(home.team)
        if agents.agent(watch):
            await emit(watch, "chat", from_=watch, text=f"{who.name} handed a brief to #{room.name}",
                       data={"trace_id": trace_id, "room": room.id})
    return task


@app.get("/api/logfire")
def logfire_project() -> dict:
    """Where the chat links a trace to: RENGA_LOGFIRE_URL, or the project
    logfire found for LOGFIRE_TOKEN (known a moment after startup)."""
    found = getattr(logfire.DEFAULT_LOGFIRE_INSTANCE.config, "_project_url", None)
    return {"url": os.environ.get("RENGA_LOGFIRE_URL") or found}


# ---- the agent library -----------------------------------------------------
@app.get("/api/library")
def library() -> dict:
    """Every premade agent, and every premade workflow."""
    from .design.roles import ROLES

    return {
        "agents": [{"id": r.id, "name": r.name, "initials": r.initials, "does": r.does,
                    "group": r.group, "senses": r.senses,
                    "personality": r.personality.model_dump()} for r in ROLES.values()],
        "workflows": [{"id": w.id, "name": w.name, "does": w.does, "how": w.how,
                       "rooms": [{"name": p.name, "purpose": p.purpose, "lead": p.lead,
                                  "members": [m.role for m in p.members]} for p in w.rooms]}
                      for w in WORKFLOWS],
    }


class StartIn(BaseModel):
    team: str


@app.post("/api/workflows/{workflow_id}/start", status_code=201)
async def start_workflow(workflow_id: str, body: StartIn) -> dict:
    """Set a workflow's rooms and agents up in a team."""
    workflow = WORKFLOWS_BY_ID.get(workflow_id)
    if not workflow:
        raise HTTPException(404, f"no workflow called {workflow_id!r}")
    if not agents.team(body.team):
        raise HTTPException(404, f"no team called {body.team!r}")
    rooms, members = workflow.build(body.team)
    named = {r.name for r in agents.all_rooms(body.team)}
    if clash := [r.name for r in rooms if r.name in named]:
        raise HTTPException(409, f"{agents.team(body.team).name} already has a #{clash[0]}. "
                                 "set this up in another team, or delete that room's team first")
    try:
        teams.add_rooms(rooms, members, taken_rooms={r.id for r in agents.all_rooms()},
                        taken_agents={a.id for a in agents.all_agents()})
    except ValueError as err:
        raise HTTPException(409, f"{err}: this workflow is already set up here") from err
    for r in rooms:
        await emit(r.id, "state", from_=r.lead, text=f"#{r.name} is set up, from the {workflow.name} workflow",
                   data={"workflow": workflow.id})
    return {"rooms": rooms, "agents": members}


@app.get("/api/events")
def events(since: int = 0, channel: str | None = None) -> list[dict]:
    return store.since(since, channel)


@app.post("/api/chat", status_code=201)
async def chat(body: ChatIn) -> dict:
    if not agents.room(body.channel):
        raise HTTPException(404, f"no room called {body.channel!r}")
    return await emit(body.channel, "chat", from_="admin", text=body.text.strip())


@app.post("/api/say", status_code=201)
async def say(body: SayIn) -> dict:
    if not agents.agent(body.agent_id):
        raise HTTPException(404, f"no agent called {body.agent_id!r}")
    if not agents.can_speak_in(body.agent_id, body.channel):
        raise HTTPException(403, f"{body.agent_id} isn't in the {body.channel!r} room")
    if body.kind in ("question", "answer"):
        raise HTTPException(422, "questions go through /api/questions")
    data = body.data
    if data and data.get("files"):
        data = {**data, "files": save_files(data["files"])}
    try:
        event = await emit(body.channel, body.kind, from_=body.agent_id, to=body.to,
                           text=body.text, data=data)
    except ValueError as err:  # the event failed validation, e.g. an unknown kind
        raise HTTPException(422, str(err)) from err
    if look := should_look(body.agent_id, body.text):
        return {**event, "look": look}  # for the extension, not the log
    return event


def should_look(speaker: str, text: str) -> dict | None:
    """A caption line that says something is being shown ("as you can see")
    asks the team's screen agent to look. The extension, which posted the
    line, takes the screenshot and sends it to /api/screen."""
    who = agents.agent(speaker)
    words = cue(text)
    if not who or "captions" not in who.senses or not words:
        return None
    team = agents.room(who.room).team
    rooms = {r.id for r in agents.all_rooms(team)}
    eyes = next((a for a in agents.all_agents() if a.room in rooms and "screen" in a.senses), None)
    if not eyes or not looks.due(eyes.room):
        return None
    return {"agent_id": eyes.id, "room": eyes.room, "because": words}


class ThinkingIn(BaseModel):
    """An agent starting a model call (`on`), or its job ending (`on` false,
    no agent: everyone in the room stops)."""

    channel: str
    agent_id: str | None = None
    on: bool = True


@app.get("/api/thinking")
def who_is_thinking() -> dict[str, list[str]]:
    return thinking.now()


@app.post("/api/thinking", status_code=201)
def set_thinking(body: ThinkingIn) -> None:
    if not body.on:
        thinking.stop(body.channel, body.agent_id)
        return
    if not body.agent_id or not agents.can_speak_in(body.agent_id, body.channel):
        raise HTTPException(403, f"{body.agent_id} isn't in the {body.channel!r} room")
    thinking.start(body.channel, body.agent_id)


class ScreenIn(BaseModel):
    """One look at a tab, sent by the extension on behalf of an agent that
    reads the screen: the page text, and a screenshot as a data url."""

    agent_id: str
    url: str = Field(max_length=2000)
    title: str = Field(default="", max_length=500)
    text: str = Field(default="", max_length=20000)
    image: str | None = Field(default=None, max_length=4_000_000)
    because: str = Field(default="", max_length=200)  # the words on the call that asked for this look
    slide: int | None = Field(default=None, ge=1, le=999)  # its number, when it's a presentation's slide


def save_frame(data_url: str) -> str:
    head, _, b64 = data_url.partition(",")
    ext = {"data:image/jpeg;base64": "jpg", "data:image/png;base64": "png"}.get(head)
    if not ext:
        raise HTTPException(422, "the screenshot should be a jpeg or png data url")
    try:
        raw = base64.b64decode(b64, validate=True)
    except binascii.Error as err:
        raise HTTPException(422, "the screenshot isn't valid base64") from err
    name = f"{uuid.uuid4().hex}.{ext}"
    (FRAMES / name).write_bytes(raw)
    return f"/frames/{name}"


FILE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,60}\.(" + "|".join(FILE_TYPES) + ")$")


def save_files(files: object) -> list[dict]:
    """The files an agent made, written to disk once every one checks out, so
    a bad one leaves nothing behind. The event keeps each one's name and
    where to get it, never the content. Names follow crew.File's rule."""
    if not isinstance(files, list) or len(files) > 8:
        raise HTTPException(422, "files should be a list of at most 8")
    for f in files:
        name = f.get("name") if isinstance(f, dict) else None
        if not isinstance(name, str) or not FILE_NAME.match(name) or not isinstance(f.get("content"), str):
            raise HTTPException(422, f"can't keep a file called {name!r}")
        if len(f["content"]) > 500_000:
            raise HTTPException(422, f"{name} is too big to keep")
    kept = []
    for f in files:
        stem, _, ext = f["name"].rpartition(".")
        stored = f"{uuid.uuid4().hex[:12]}-{stem}.{ext}"
        (FILES / stored).write_text(f["content"])
        kept.append({"name": f["name"], "url": f"/files/{stored}", "type": FILE_TYPES[ext],
                     "size": len(f["content"])})
    return kept


@app.get("/files/{name}")
def get_file(name: str) -> Response:
    """An agent's file. Served sandboxed: an html or svg it made can't run
    scripts or reach renga, even opened in its own tab."""
    path = FILES / name
    ext = name.rpartition(".")[2]
    if "/" in name or name.startswith(".") or ext not in FILE_TYPES or not path.is_file():
        raise HTTPException(404, "no such file")
    return Response(path.read_bytes(), media_type=FILE_TYPES[ext],
                    headers={"Content-Security-Policy": "sandbox; default-src 'none'; "
                                                        "style-src 'unsafe-inline'; img-src data:; font-src data:",
                             "X-Content-Type-Options": "nosniff"})


@app.post("/api/screen", status_code=201)
async def screen(body: ScreenIn) -> dict:
    who = agents.agent(body.agent_id)
    if not who:
        raise HTTPException(404, f"no agent called {body.agent_id!r}")
    if "screen" not in who.senses:
        raise HTTPException(403, f"{who.name} doesn't read the screen")
    data = {"url": body.url, "title": body.title, "text": body.text[:4000]}
    if body.image:
        data["frame"] = save_frame(body.image)
    said = f"read the screen: {body.title or body.url}"
    if body.slide:
        data["slide"] = body.slide
        said = f"saw slide {body.slide} of the presentation"
    elif body.because:
        data["because"] = body.because
        said = f'looked at the screen, because someone said "{body.because}"'
    return await emit(who.room, "tool_result", from_=who.id, text=said, data=data)


@app.get("/api/questions")
def open_questions(channel: str | None = None) -> list[dict]:
    return questions.open(channel)


@app.post("/api/questions", status_code=201)
async def ask(body: QuestionIn) -> dict:
    if not agents.agent(body.agent_id):
        raise HTTPException(404, f"no agent called {body.agent_id!r}")
    if not agents.can_speak_in(body.agent_id, body.channel):
        raise HTTPException(403, f"{body.agent_id} isn't in the {body.channel!r} room")
    q = questions.add(body)
    await emit(body.channel, "question", from_=body.agent_id, text=body.text,
               data={"question_id": q["id"], "options": body.options, "blocking": body.blocking})
    return q


@app.post("/api/questions/{qid}/answer")
async def answer(qid: int, body: AnswerIn) -> dict:
    q = questions.get(qid)
    if not q:
        raise HTTPException(404, "no such question")
    if not questions.answer(qid, body.value.strip()):
        raise HTTPException(409, "already answered")
    await emit(q["channel"], "answer", from_="admin", to=q["agent_id"], text=body.value.strip(),
               data={"question_id": qid})
    return questions.get(qid)


@app.get("/api/extension.zip")
def extension_zip(request: Request) -> Response:
    """The chrome extension as a zip to unpack and load, pointed at the server
    it was downloaded from, so it works on whatever port this runs on."""
    origin = str(request.base_url).rstrip("/")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(EXTENSION.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            text = f.read_text() if f.suffix in (".js", ".json", ".html", ".css") else None
            if text is None:
                z.write(f, f"renga/{f.name}")
                continue
            text = text.replace("http://localhost:8020", origin)
            if f.name == "manifest.json":
                manifest = json.loads(text)
                manifest["host_permissions"] = [f"{origin}/*"] + [
                    h for h in manifest["host_permissions"] if not h.startswith(origin)]
                text = json.dumps(manifest, indent=2) + "\n"
            z.writestr(f"renga/{f.name}", text)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="renga-extension.zip"'})


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await bus.connect(socket)
    try:
        while True:
            await socket.receive_text()  # clients only listen; this keeps the socket open
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await bus.disconnect(socket)


# The chrome extension's files too, so the side panel can be opened in an
# ordinary tab while working on it (it works without the chrome apis).
app.mount("/extension", StaticFiles(directory=EXTENSION), name="extension")
app.mount("/frames", StaticFiles(directory=FRAMES), name="frames")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
