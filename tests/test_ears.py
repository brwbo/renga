import asyncio
import base64

from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from renga.design.ears import Ears
from renga.design.inside import stream
from renga.design.jobs import hear_job
from renga.design.sandbox import pump

WAV = base64.b64encode(b"RIFF....WAVEfmt not really audio").decode()


def hear(client, agent="transcript", audio=WAV, mime="audio/wav"):
    return client.post("/api/hear", json={"agent_id": agent, "audio": audio, "mime": mime})


def test_the_call_audio_waits_for_the_host_a_room_at_a_time(client):
    assert hear(client).json() == {"room": "main", "waiting": 1}
    assert hear(client, audio=base64.b64encode(b"second").decode()).json()["waiting"] == 2
    assert client.post("/api/heard/next", json={"busy": ["main"]}).json() == []  # still on the last one
    first = client.post("/api/heard/next", json={}).json()
    assert [(c["room"], c["agent_id"], c["audio"]) for c in first] == [("main", "transcript", WAV)]
    assert client.post("/api/heard/next", json={}).json()[0]["audio"] == base64.b64encode(b"second").decode()
    assert client.post("/api/heard/next", json={}).json() == []
    assert client.get("/api/events?channel=main").json() == []  # audio never goes in the log


def test_only_the_agent_that_hears_the_call_can_send_it(client):
    assert hear(client, agent="nobody").status_code == 404
    assert hear(client, agent="visual").status_code == 403
    assert hear(client, mime="audio/webm").status_code == 422
    assert hear(client, audio="not base64!").status_code == 422


def transcribing(said: list[dict], got: list) -> FunctionModel:
    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        got.extend(p for m in messages for part in m.parts if isinstance(part, UserPromptPart)
                   for p in (part.content if isinstance(part.content, list) else [part.content]))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"lines": said})])
    return FunctionModel(reply)


def test_the_ears_hear_the_audio_and_post_a_line_per_turn():
    got = []
    ears = Ears("main", "transcript", model=transcribing(
        [{"who": "sam", "text": "we need the fx email by thursday"}, {"who": "speaker 2", "text": "  "}], got))

    async def go():
        return [line async for line in ears.run(b"audio", "audio/wav", ["sam: morning all"])]

    lines = asyncio.run(go())
    assert [(line.agent_id, line.kind, line.text) for line in lines] == [
        ("transcript", "chat", "sam: we need the fx email by thursday")]  # the blank turn is dropped
    audio = [p for p in got if isinstance(p, BinaryContent)]
    assert audio and audio[0].data == b"audio" and audio[0].media_type == "audio/wav"
    assert any("sam: morning all" in p for p in got if isinstance(p, str))  # who's who so far


def test_a_chunk_becomes_transcript_the_pm_reads(client):
    client.post("/api/say", json={"agent_id": "transcript", "channel": "main",
                                  "text": "sam: morning all"}).raise_for_status()
    rooms = client.get("/api/rooms").json()
    room = next(r for r in rooms if r["id"] == "main")
    job = hear_job(room, "transcript", WAV, "audio/wav", client.get("/api/events?channel=main").json())
    assert job.kind == "hear" and job.me == "transcript" and job.seen == ["sam: morning all"]

    async def printed():
        return [o async for o in stream(job, model=transcribing([{"who": "sam", "text": "fx email by thursday"}], []))]

    pump(asyncio.run(printed()), lambda path, body: client.post(path, json=body).raise_for_status())
    last = client.get("/api/events?channel=main").json()[-1]
    assert (last["from"], last["kind"], last["text"]) == ("transcript", "chat", "sam: fx email by thursday")


def test_the_worker_runs_jobs_side_by_side_and_tags_each_line():
    import json
    import queue

    from renga.design.inside import serve
    from renga.design.jobs import Job

    jobs = [Job(kind="hear", room="main", me="transcript", audio=WAV, mime="audio/wav", seen=[]),
            Job(kind="hear", room="main", me="transcript", audio=WAV, mime="audio/wav", seen=[])]
    stdin = queue.Queue()
    for n, job in enumerate(jobs):
        stdin.put(json.dumps({"id": f"j{n}", "job": job.model_dump(mode="json")}) + "\n")
    stdin.put("")  # stdin closed: finish what's running and stop
    out: list[dict] = []
    model = transcribing([{"who": "sam", "text": "fx email by thursday"}], [])
    asyncio.run(serve(read=stdin.get, write=lambda text: out.append(json.loads(text)), model=model))
    for jid in ("j0", "j1"):
        mine = [m for m in out if m["id"] == jid]
        assert json.loads(mine[0]["line"])["text"] == "sam: fx email by thursday"
        assert mine[-1] == {"id": jid, "done": True}


def test_chunks_are_posted_in_the_order_they_were_said():
    from renga.design.crew import Line
    from renga.design.sandbox import InOrder

    said = lambda text: Line(agent_id="transcript", channel="main", kind="chat", text=text)  # noqa: E731
    posted: list[str] = []
    post = lambda path, body: posted.append(body["text"])  # noqa: E731
    order = InOrder()
    first, second, third = order.ticket(), order.ticket(), order.ticket()
    order.finish(third, [said("three")], post)   # finishes first, waits its turn
    order.finish(second, [], post)               # nobody spoke
    assert posted == []
    order.finish(first, [said("one"), said("one more")], post)
    assert posted == ["one", "one more", "three"]
