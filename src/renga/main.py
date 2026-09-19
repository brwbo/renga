"""The server: the event log over http and a websocket, the teams and their
rooms, delegation between them, and the question queue. Serves the chat app in web/ at /."""

import contextlib
from pathlib import Path

import logfire
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agents
from .bus import bus, emit
from .db import store
from .questions import QuestionIn
from .questions import store as questions

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
EXTENSION = ROOT / "extension"

logfire.configure(send_to_logfire="if-token-present", console=False)

app = FastAPI(title="renga")


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
    return agents.ROSTER


@app.get("/api/teams")
def list_teams() -> list[agents.Team]:
    return agents.TEAMS


class DelegateIn(BaseModel):
    """The pm handing a piece of work to another team."""

    team: str
    text: str = Field(min_length=1, max_length=8000)
    data: dict | None = None


@app.post("/api/delegate", status_code=201)
async def delegate(body: DelegateIn) -> dict:
    team = agents.TEAM_BY_ID.get(body.team)
    if not team or team.id == "main":
        raise HTTPException(404, f"no team called {body.team!r} to delegate to")
    # One line in the meeting room so you can see where the work went, and
    # the brief itself in the team's room, addressed to its lead.
    await emit("main", "handoff", from_="pm", to=f"team:{team.id}",
               text=f"sent to the {team.name} team: {body.text}", data={"team": team.id})
    return await emit(team.id, "task", from_="pm", to=team.lead, text=body.text,
                      data={**(body.data or {}), "delegated_from": "main"})


@app.get("/api/events")
def events(since: int = 0, channel: str | None = None) -> list[dict]:
    return store.since(since, channel)


@app.post("/api/chat", status_code=201)
async def chat(body: ChatIn) -> dict:
    if body.channel not in agents.TEAM_BY_ID:
        raise HTTPException(404, f"no room called {body.channel!r}")
    return await emit(body.channel, "chat", from_="admin", text=body.text.strip())


@app.post("/api/say", status_code=201)
async def say(body: SayIn) -> dict:
    if body.agent_id not in agents.BY_ID:
        raise HTTPException(404, f"no agent called {body.agent_id!r}")
    if not agents.can_speak_in(body.agent_id, body.channel):
        raise HTTPException(403, f"{body.agent_id} isn't in the {body.channel!r} room")
    if body.kind in ("question", "answer"):
        raise HTTPException(422, "questions go through /api/questions")
    try:
        return await emit(body.channel, body.kind, from_=body.agent_id, to=body.to,
                          text=body.text, data=body.data)
    except ValueError as err:  # the event failed validation, e.g. an unknown kind
        raise HTTPException(422, str(err)) from err


@app.get("/api/questions")
def open_questions(channel: str | None = None) -> list[dict]:
    return questions.open(channel)


@app.post("/api/questions", status_code=201)
async def ask(body: QuestionIn) -> dict:
    if body.agent_id not in agents.BY_ID:
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
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
