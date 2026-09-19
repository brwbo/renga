import asyncio
import base64

from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from renga.design.inside import stream
from renga.design.jobs import aide, eyes_job, notes_job, router_job
from renga.design.sandbox import look, pump

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082")).decode()


def answering(args: dict, seen: list | None = None) -> FunctionModel:
    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(messages[-1].parts[-1].content)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])
    return FunctionModel(reply)


def run_job(client, job, model):
    async def printed():
        return [o async for o in stream(job, model=model)]
    return pump(asyncio.run(printed()), lambda path, body: client.post(path, json=body).raise_for_status())


def meeting(client, lines=("sam: the launch is friday", "priya: i'll own the post")):
    client.post("/api/workflows/meeting-to-marketing/start", json={"team": "rowbo"}).raise_for_status()
    for text in lines:
        client.post("/api/say", json={"agent_id": "rowbo-meeting-listener", "channel": "rowbo-meeting",
                                      "text": text}).raise_for_status()
    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    room = next(r for r in rooms if r["id"] == "rowbo-meeting")
    return room, rooms, agents, client.get("/api/events?channel=rowbo-meeting").json()


def test_the_meeting_room_has_a_note_taker_and_a_visualiser(client):
    room, rooms, agents, _ = meeting(client)
    assert aide(room, agents, "note-taker")["id"] == "rowbo-meeting-note-taker"
    assert aide(room, agents, "visualiser")["senses"] == ["screen"]
    assert aide(next(r for r in rooms if r["id"] == "rowbo-marketing"), agents, "note-taker") is None


def test_the_note_taker_keeps_the_notes(client):
    room, rooms, agents, log = meeting(client)
    job = notes_job(room, agents, log, since=log[0]["id"])
    assert job.me == "rowbo-meeting-note-taker" and job.notes == ""
    assert job.new == ["listener: sam: the launch is friday", "listener: priya: i'll own the post"]

    run_job(client, job, answering({"changed": True, "summary": ["the launch"],
                                    "decisions": ["launch friday (sam)"], "owed": ["priya: the post"]}))
    card = client.get("/api/events?channel=rowbo-meeting").json()[-1]
    assert card["from"] == "rowbo-meeting-note-taker" and card["kind"] == "chat"
    assert "## decisions\n\n- launch friday (sam)" in card["data"]["deliverable"]
    assert "## open" not in card["data"]["deliverable"]

    # the next run starts from those notes, and the notes aren't the meeting to anyone
    log = client.get("/api/events?channel=rowbo-meeting").json()
    again = notes_job(room, agents, log, since=card["id"] - 1)
    assert again.notes == card["data"]["deliverable"] and again.new == []
    assert router_job(room, rooms, agents, log, since=card["id"] - 1).new == []

    # nothing new worth keeping: nothing posted
    run_job(client, job, answering({"changed": False}))
    assert client.get("/api/events?channel=rowbo-meeting").json()[-1]["id"] == card["id"]


def test_the_visualiser_writes_down_the_screen_and_makes_nothing(client):
    room, rooms, agents, log = meeting(client, ["sam: first legal signs off, then brand, then we post"])
    r = client.post("/api/screen", json={"agent_id": "rowbo-meeting-visualiser", "url": "https://x.test/q3",
                                        "title": "q3 plan", "text": "revenue 4.2m",
                                        "image": f"data:image/png;base64,{PNG}"})
    assert r.status_code == 201, r.text
    screen = look(client, r.json())
    assert screen.title == "q3 plan" and screen.media_type == "image/png"
    assert base64.b64decode(screen.image) == base64.b64decode(PNG)

    log = client.get("/api/events?channel=rowbo-meeting").json()
    job = eyes_job(room, agents, log, since=log[0]["id"], screen=screen)
    assert job.me == "rowbo-meeting-visualiser"
    assert job.new == ["listener: sam: first legal signs off, then brand, then we post"]

    seen: list = []
    run_job(client, job, answering({"say": "the q3 plan", "notes": "# q3 plan\n\n- revenue 4.2m"}, seen))
    assert any(isinstance(p, BinaryContent) for p in seen[0])  # it saw the screenshot
    assert any("revenue 4.2m" in p for p in seen[0] if isinstance(p, str))
    wrote = client.get("/api/events?channel=rowbo-meeting").json()[-1]
    assert wrote["from"] == "rowbo-meeting-visualiser" and wrote["text"] == "the q3 plan"
    assert wrote["data"]["notes"] == "# q3 plan\n\n- revenue 4.2m" and "files" not in wrote["data"]

    # what it wrote isn't the meeting, it's what the project manager briefs with
    log = client.get("/api/events?channel=rowbo-meeting").json()
    job = router_job(room, rooms, agents, log, since=wrote["id"] - 1)
    assert job.new == [] and job.slides == ["on screen (q3 plan):\n# q3 plan\n\n- revenue 4.2m"]


def test_the_visualiser_only_talks_when_it_has_something(client):
    room, _, agents, log = meeting(client)
    job = eyes_job(room, agents, log, since=log[0]["id"])
    before = client.get("/api/events?channel=rowbo-meeting").json()[-1]["id"]
    run_job(client, job, answering({"say": "", "diagram": None}))
    assert client.get("/api/events?channel=rowbo-meeting").json()[-1]["id"] == before
