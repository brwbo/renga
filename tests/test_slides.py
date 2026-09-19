import asyncio
import base64

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
        {"say": "slide 2: q3 revenue, up 18%", "notes": "# q3 revenue\n\n- up 18% on q2\n- emea 41%"}, prompts))

    async def go():
        screen = Screen(title="q3 review", image=base64.b64encode(b"img").decode(), media_type="image/png", slide=2)
        return [line async for line in eyes.run([], [], screen) if line.kind != "thinking"]

    [line] = asyncio.run(go())
    assert line.text == "slide 2: q3 revenue, up 18%\n\n# q3 revenue\n\n- up 18% on q2\n- emea 41%"
    assert line.data == {"slide": 2, "notes": "# q3 revenue\n\n- up 18% on q2\n- emea 41%", "shown": "slide 2"}
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
    assert any("what's been shown on screen in this meeting" in p and "up 18%" in p for p in prompts)


def test_the_visualiser_never_makes_material():
    from renga.design.visualiser import Seen
    assert set(Seen.model_fields) == {"say", "notes"}  # no files, no diagram: nothing to post but notes
    prompts = []
    eyes = Visualiser("main", "visual", model=answering({"say": "x", "notes": "x"}, prompts))

    async def go():  # nothing on screen to look at: it doesn't run at all
        return [line async for line in eyes.run(["person: make me a linkedin post"], [], None)]

    assert asyncio.run(go()) == [] and prompts == []
