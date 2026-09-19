"""The room's server: the event log over http and a websocket, the roster,
and the question queue. Serves the chat app in web/ at /."""

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

WEB = Path(__file__).resolve().parents[2] / "web"

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


@app.get("/api/events")
def events(since: int = 0, channel: str = "main") -> list[dict]:
    return store.since(since, channel)


@app.post("/api/chat", status_code=201)
async def chat(body: ChatIn) -> dict:
    return await emit(body.channel, "chat", from_="admin", text=body.text.strip())


@app.post("/api/say", status_code=201)
async def say(body: SayIn) -> dict:
    if body.agent_id not in agents.BY_ID:
        raise HTTPException(404, f"no agent called {body.agent_id!r} in the room")
    if body.kind in ("question", "answer"):
        raise HTTPException(422, "questions go through /api/questions")
    try:
        return await emit(body.channel, body.kind, from_=body.agent_id, to=body.to,
                          text=body.text, data=body.data)
    except ValueError as err:  # the event failed validation, e.g. an unknown kind
        raise HTTPException(422, str(err)) from err


@app.get("/api/questions")
def open_questions(channel: str = "main") -> list[dict]:
    return questions.open(channel)


@app.post("/api/questions", status_code=201)
async def ask(body: QuestionIn) -> dict:
    if body.agent_id not in agents.BY_ID:
        raise HTTPException(404, f"no agent called {body.agent_id!r} in the room")
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


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
