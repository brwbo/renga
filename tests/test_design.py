import asyncio
import json
from typing import get_args

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from renga.design.crew import Assignment, Crew, Line, waves
from renga.design.personality import Character, Personality, voice
from renga.design.presets import PRESETS, PRESETS_BY_ID, Member, Preset
from renga.design.roles import ROLES, DesignRoleId


def test_sixteen_roles_and_seven_teams():
    assert len(get_args(DesignRoleId)) == 16
    assert set(ROLES) == set(get_args(DesignRoleId)) | {"listener", "project-manager"}
    assert len({r.initials for r in ROLES.values()}) == len(ROLES)
    assert {r.group for r in ROLES.values()} == {"meeting", "design", "marketing"}
    assert [p.id for p in PRESETS] == ["full-studio", "landing-page-sprint", "brand-campaign",
                                       "content-machine", "product-team", "full-stack-design",
                                       "marketing-blitz"]
    assert len(PRESETS_BY_ID["full-studio"].members) == 16


def test_each_team_has_the_right_lead():
    leads = {p.id: p.lead for p in PRESETS}
    assert leads["brand-campaign"] == "creative-director"
    assert leads["marketing-blitz"] == "marketing-strategist"  # the one with the leader trait
    assert leads["full-stack-design"] == "brand-strategist"
    assert leads["landing-page-sprint"] == "researcher"  # nobody leads, so the first


def test_traits_and_sliders_are_checked():
    with pytest.raises(ValidationError):
        Personality(bold_subtle=6)
    with pytest.raises(ValidationError):
        Character(traits=["sassy", "chill", "intense"])  # three temperaments
    with pytest.raises(ValidationError):
        Character(traits=["sassy", "sassy"])
    with pytest.raises(ValidationError):
        Member(role="copywriter", traits=["grumpy"])
    with pytest.raises(ValidationError):
        Preset(id="twins", does="x", members=[Member(role="copywriter"), Member(role="copywriter")])


def test_voice_reads_the_sliders_and_traits():
    assert voice(Personality()) == "you have a neutral, balanced way of talking."
    loud = voice(Personality(bold_subtle=-4, playful_serious=-3), ["sassy"])
    assert "a very bold tone" in loud and "irreverent" in loud and "quick and sharp" in loud


def test_waves_follow_the_dependencies():
    a = [Assignment(role="graphic-designer", task="x", after=["copywriter"]),
         Assignment(role="copywriter", task="x", after=["researcher"]),
         Assignment(role="researcher", task="x")]
    assert [[x.role for x in w] for w in waves(a)] == [["researcher"], ["copywriter"], ["graphic-designer"]]
    with pytest.raises(ValueError):
        waves([Assignment(role="copywriter", task="x", after=["researcher"]),
               Assignment(role="researcher", task="x", after=["copywriter"])])


# ---- a whole team, with a scripted model instead of claude -----------------
def scripted(calls: list[str]):
    """Answers as whichever part of the crew is asking: the lead's plan (the
    first try names someone off the team, to check it gets sent back), the
    specialists' work, and a review that asks the copywriter for one more pass."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        fields = tool.parameters_json_schema["properties"]
        retried = any(isinstance(p, RetryPromptPart) for m in messages for p in m.parts)
        if "assignments" in fields:
            calls.append("plan")
            copy = {"role": "copywriter", "task": "write the post"}
            if not retried:
                args = {"say": "on it", "assignments": [copy, {"role": "print-designer", "task": "x"}]}
            else:
                args = {"say": "copy first, then visuals", "assignments": [
                    copy, {"role": "graphic-designer", "task": "make the image", "after": ["copywriter"]}]}
        elif "approved" in fields:
            calls.append("review")
            args = {"say": "close, one more pass on the copy", "approved": False,
                    "notes": [{"role": "copywriter", "note": "the hook is buried"}]}
        else:
            prompt = json.dumps([str(p) for m in messages for p in m.parts])
            calls.append("work")
            args = {"say": "done", "deliverable": f"work for: {prompt[-40:]}",
                    "ask": {"text": "can we name priya?", "options": ["yes", "no"]}
                    if "write the post" in prompt else None}
        return ModelResponse(parts=[ToolCallPart(tool.name, args)])

    return FunctionModel(reply)


def run(crew: Crew, brief: str) -> list[Line]:
    async def go():
        return [line async for line in crew.run(brief)]
    return asyncio.run(go())


def test_a_team_plans_works_reviews_and_revises():
    calls: list[str] = []
    crew = Crew(PRESETS_BY_ID["brand-campaign"], model=scripted(calls))
    lines = run(crew, "a linkedin post about onboarding in a day")
    assert calls[:2] == ["plan", "plan"]  # the print designer isn't on this team
    assert calls.count("review") == 1 and calls.count("work") == 3  # copy, image, copy again
    who = [(line.agent_id.removeprefix("brand-campaign-"), line.kind) for line in lines]
    assert who[:3] == [("creative-director", "announce_start"), ("creative-director", "chat"),
                       ("creative-director", "task")]
    assert who.index(("copywriter", "announce_done")) < who.index(("graphic-designer", "announce_done"))
    assert ("copywriter", "question") in who
    assert who[-1] == ("creative-director", "announce_done")
    assert set(lines[-1].data["deliverables"]) == {"copywriter", "graphic-designer"}
    assert all(line.channel == "brand-campaign" for line in lines)


def test_everything_a_team_says_lands_in_its_room(client):
    lines = run(Crew(PRESETS_BY_ID["brand-campaign"], model=scripted([])), "a post")
    for line in lines:
        path, body = line.request()
        assert client.post(path, json=body).status_code == 201, body
    events = client.get("/api/events?channel=brand-campaign").json()
    assert len(events) == len(lines)
    assert [q["agent_id"] for q in client.get("/api/questions").json()] == ["brand-campaign-copywriter"]


def test_every_team_and_member_is_in_renga(client):
    rooms = {r["id"]: r for r in client.get("/api/rooms").json()}
    agents = {a["id"]: a for a in client.get("/api/agents").json()}
    for p in PRESETS:
        crew = Crew(p, model=scripted([]))
        assert rooms[p.id]["lead"] == crew.id(p.lead)
        assert all(agents[crew.id(m.role)]["room"] == p.id for m in p.members)


# ---- the sandbox: what runs inside it, and what posts its output ------------
def test_what_the_sandbox_prints_gets_posted_into_the_room(client):
    from renga.design.inside import stream
    from renga.design.jobs import crew_job
    from renga.design.sandbox import pump

    room = next(r for r in client.get("/api/rooms").json() if r["id"] == "brand-campaign")
    job = crew_job(room, client.get("/api/agents").json(), "a post")

    async def printed():
        return [out async for out in stream(job, model=scripted([]))]

    out = [o + "\n" for o in asyncio.run(printed())] + ["\n"]
    posted = pump(out, lambda path, body: client.post(path, json=body).raise_for_status())
    assert posted == len(out) - 1
    room = client.get("/api/events?channel=brand-campaign").json()
    watched = client.get("/api/events?channel=logfire").json()  # started, finished
    assert len(room) + len(watched) == posted and len(watched) >= 2
    assert len(client.get("/api/questions").json()) == 1


def test_the_sandbox_name_follows_the_code():
    from renga.design import sandbox

    before = sandbox.version()
    assert len(before) == 8 and sandbox.version() == before


def test_the_model_picks_the_key_and_the_host(monkeypatch):
    from renga.design import sandbox

    assert sandbox.provider("anthropic:claude-sonnet-5") == ("anthropic", "api.anthropic.com")
    assert sandbox.provider("google:gemini-3.1-pro-preview") == ("gemini", "generativelanguage.googleapis.com")
    with pytest.raises(SystemExit):
        sandbox.provider("openai:gpt-5")
    claude = sandbox.version()
    monkeypatch.setenv("RENGA_MODEL", "google:gemini-3.1-pro-preview")
    assert sandbox.version() != claude  # a new model gets a new sandbox


def test_the_logfire_agent_posts_each_run_into_its_room(client):
    import logfire

    from renga.design.inside import WATCH, stream
    from renga.design.jobs import crew_job
    from renga.design.sandbox import pump

    logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[WATCH])
    logfire.instrument_pydantic_ai()
    task = client.post("/api/delegate", json={"room": "brand-campaign", "text": "a post"}).json()
    parent = task["data"]["traceparent"]

    room = next(r for r in client.get("/api/rooms").json() if r["id"] == "brand-campaign")
    job = crew_job(room, client.get("/api/agents").json(), "a post", traceparent=parent)

    async def printed():
        return [out async for out in stream(job, model=scripted([]))]

    pump(asyncio.run(printed()), lambda path, body: client.post(path, json=body).raise_for_status())
    lines = client.get("/api/events?channel=logfire").json()
    texts = [e["text"] for e in lines]
    assert texts[0] == "pm handed a brief to #brand-campaign"
    assert texts[1] == "#brand-campaign started on a brief"
    assert any(t.startswith("#brand-campaign: creative director (plan) took") for t in texts)
    assert texts[-1].startswith("#brand-campaign finished: 5 agent runs")
    # the hand-off and the team's run are one trace
    assert {e["data"]["trace_id"] for e in lines} == {parent.split("-")[1]}
