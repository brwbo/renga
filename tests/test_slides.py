import asyncio
import base64
import time

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from renga.design.jobs import aide, router_job, slides
from renga.design.router import Router, Target
from renga.design.visualiser import Screen, Visualiser

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nnot really").decode()


def answering(args: dict, prompts: list | None = None) -> FunctionModel:
    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if prompts is not None:
            prompts.extend(str(p) for m in messages for part in m.parts if isinstance(part, UserPromptPart)
                           for p in (part.content if isinstance(part.content, list) else [part.content]))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])
    return FunctionModel(reply)


def test_renga_and_aurelia_have_a_visualiser_that_reads_the_screen(client):
    rooms = {r["id"]: r for r in client.get("/api/rooms").json()}
    agents = client.get("/api/agents").json()
    assert aide(rooms["main"], agents, "visualiser")["id"] == "visual"
    assert aide(rooms["aurelia-meeting"], agents, "visualiser")["id"] == "aurelia-visual"


def test_a_slide_is_seen_as_a_slide(client):
    r = client.post("/api/screen", json={"agent_id": "visual", "url": "https://meet.google.com/abc",
                                         "title": "q3 review", "image": PNG, "slide": 2})
    e = r.json()
    assert e["text"] == "saw slide 2 of the presentation" and e["data"]["slide"] == 2
    assert client.post("/api/screen", json={"agent_id": "visual", "url": "x", "slide": 0}).status_code == 422


def test_the_visualiser_writes_down_everything_on_a_slide():
    prompts = []
    eyes = Visualiser("main", "visual", model=answering(
        {"found": ["q3 revenue up 18% on q2", "- emea is 41% of it", " "]}, prompts))

    async def go():
        screen = Screen(title="q3 review", image=base64.b64encode(b"img").decode(), media_type="image/png", slide=2)
        return [line async for line in eyes.run([], [], screen) if line.kind != "thinking"]

    [line] = asyncio.run(go())
    assert line.text == "- q3 revenue up 18% on q2\n- emea is 41% of it"
    assert line.data == {"slide": 2, "notes": line.text, "shown": "slide 2", "quiet": True}
    assert any("this is slide 2" in p for p in prompts)


def test_the_pm_has_every_slide_shown(client):
    def slide(n, notes):
        client.post("/api/say", json={"agent_id": "visual", "channel": "main", "text": f"slide {n}",
                                      "data": {"slide": n, "notes": notes}}).raise_for_status()
    slide(1, "# agenda")
    slide(2, "# q3 revenue\n- up 17%")
    slide(2, "# q3 revenue\n- up 18%")  # shown again, read again: the latest counts
    client.post("/api/chat", json={"channel": "main", "text": "make a post about q3"}).raise_for_status()
    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    meeting = next(r for r in rooms if r["id"] == "main")
    log = client.get("/api/events?channel=main").json()
    assert slides(meeting, agents, log) == ["slide 1:\n# agenda", "slide 2:\n# q3 revenue\n- up 18%"]
    job = router_job(meeting, rooms, agents, log, since=0)
    assert job.slides == slides(meeting, agents, log)
    assert job.new == ["person: make a post about q3"]  # the slides are context, not the meeting

    prompts = []
    router = Router("main", "pm", [Target(room="design", name="design")], model=answering({}, prompts))

    async def go():
        return [line async for line in router.run(job.seen, job.new, job.slides)]

    asyncio.run(go())
    assert any("the visualiser's notes on what's been shown on screen" in p and "up 18%" in p for p in prompts)


def test_the_visualiser_never_makes_material():
    from renga.design.visualiser import Seen
    assert set(Seen.model_fields) == {"found"}  # no files, no diagram: nothing to post but what it found
    prompts = []
    eyes = Visualiser("main", "visual", model=answering({"found": ["x"]}, prompts))

    async def go():  # nothing on screen to look at: it doesn't run at all
        return [line async for line in eyes.run(["person: make me a linkedin post"], [], None)]

    assert asyncio.run(go()) == [] and prompts == []


def test_the_visualiser_says_nothing_when_a_slide_has_nothing_useful():
    prompts = []
    eyes = Visualiser("main", "visual", model=answering({"found": []}, prompts))
    image = base64.b64encode(b"img").decode()

    async def go(screen):
        return [line async for line in eyes.run([], [], screen) if line.kind != "thinking"]

    # only the call on screen: a quiet line, so the notes file knows slide 3 was read
    [line] = asyncio.run(go(Screen(image=image, media_type="image/png", slide=3)))
    assert line.data == {"notes": "", "shown": "slide 3", "slide": 3, "quiet": True}
    assert asyncio.run(go(Screen(image=image, media_type="image/png", title="a tab"))) == []  # asked by hand: silent
    assert prompts  # it did look
    prompts.clear()  # "as you can see" with nobody presenting: it doesn't look at all
    assert asyncio.run(go(Screen(image=image, media_type="image/png", because="as you can see"))) == []
    assert prompts == []


def test_the_notes_on_the_slides_come_out_as_one_file_when_the_presentation_ends(client, monkeypatch):
    from renga import main
    monkeypatch.setattr(main, "DECK_WAIT", 3)
    assert client.post("/api/deck", json={"agent_id": "visual", "state": "start"}).status_code == 202
    for n in (1, 2, 3):
        client.post("/api/screen", json={"agent_id": "visual", "url": "https://meet.google.com/x",
                                         "title": "meet", "slide": n}).raise_for_status()
    for n, notes in ((1, "- 9 banks connected"), (2, ""), (3, "- runs at 02:00, 55-90 min")):
        client.post("/api/say", json={"agent_id": "visual", "channel": "main", "text": notes or "nothing",
                                      "data": {"slide": n, "notes": notes, "quiet": True}}).raise_for_status()
    assert client.post("/api/deck", json={"agent_id": "visual", "state": "done"}).status_code == 202
    for _ in range(50):
        last = client.get("/api/events?channel=main").json()[-1]
        if (last.get("data") or {}).get("deck") == "done":
            break
        time.sleep(0.1)
    assert last["text"] == "here are my notes on the slides."
    [f] = last["data"]["files"]
    assert f["name"] == "slides.md"
    md = client.get(f["url"]).text
    assert md == "# notes on the slides\n\n## slide 1\n\n- 9 banks connected\n\n## slide 3\n\n- runs at 02:00, 55-90 min\n"

    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    meeting = next(r for r in rooms if r["id"] == "main")
    log = client.get("/api/events?channel=main").json()
    assert slides(meeting, agents, log) == ["slide 1:\n- 9 banks connected", "slide 3:\n- runs at 02:00, 55-90 min"]


def test_the_pm_waits_for_the_notes_while_someone_presents():
    from renga.deck import presenting, unread
    start = {"from": "v", "kind": "chat", "data": {"deck": "start"}}
    look = {"from": "v", "kind": "tool_result", "data": {"slide": 1}}
    read = {"from": "v", "kind": "chat", "data": {"slide": 1, "notes": "- x", "quiet": True}}
    done = {"from": "v", "kind": "chat", "data": {"deck": "done"}}
    assert presenting([start, look], "v") and unread([start, look], "v") == {1}
    assert presenting([start, look, read], "v") and unread([start, look, read], "v") == set()
    assert not presenting([start, look, read, done], "v") and not presenting([], "v")
