import asyncio

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from renga.design.crew import HOUSE_RULES
from renga.design.jobs import router_job
from renga.design.router import Router, Target

DESIGN = [Target(room="design", name="design", purpose="copy, visuals, social")]


def replying(*answers: dict) -> FunctionModel:
    """Gives each answer in turn, one per model call."""
    left = list(answers)

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, left.pop(0))])

    return FunctionModel(reply)


def run(router: Router, new: list[str]):
    async def go():
        return [line async for line in router.run([], new) if line.kind != "thinking"]
    return asyncio.run(go())


def test_the_pm_asks_for_what_the_brief_would_have_to_guess():
    router = Router("main", "pm", DESIGN, model=replying({
        "say": "on it, one thing first",
        "needs": [{"work": "the savings launch post", "room": "design",
                   "asks": ["what's the rate?", "when does it launch?"]}]}))
    lines = run(router, ["person: a linkedin post for the new savings account"])
    assert [(line.kind, line.to) for line in lines] == [("chat", None), ("chat", None)]  # nothing handed off
    assert lines[1].text == ("before the savings launch post goes to #design, i need:\n"
                             "- what's the rate?\n- when does it launch?")
    assert lines[1].data["need"]["room"] == "design"


def test_once_answered_the_work_goes():
    router = Router("main", "pm", DESIGN, model=replying({
        "say": "sent it to design", "handoffs": [{"room": "design", "brief": "launch post, 4.1% rate, live monday"}]}))
    lines = run(router, ["person: 4.1%, live monday"])
    assert [line.kind for line in lines] == ["chat", "delegate"] and "4.1%" in lines[1].text


def test_a_need_for_a_room_that_isnt_there_is_sent_back():
    router = Router("main", "pm", DESIGN, model=replying(
        {"needs": [{"work": "a post", "room": "marketing", "asks": ["the rate?"]}]},
        {"needs": [{"work": "a post", "room": "design", "asks": ["the rate?"]}]}))
    assert run(router, ["person: a post"])[0].text.startswith("before a post goes to #design")


def test_the_pm_is_told_to_check_the_context_first_and_hold_the_work():
    seen = []

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info.instructions or "")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {})])

    run(Router("main", "pm", DESIGN, model=FunctionModel(reply), context="rates: 4.1%"), ["person: hi"])
    text = seen[0]
    assert "never ask for what either already says" in text and "that work waits" in text
    assert "rates: 4.1%" in text
    assert "never make up a\nfact" in HOUSE_RULES


def test_the_pm_sees_what_it_is_still_waiting_on(client):
    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    meeting = next(r for r in rooms if r["id"] == "main")
    client.post("/api/say", json={"agent_id": "pm", "channel": "main",
                                  "text": "before the post goes to #design, i need:\n- the rate?"}).raise_for_status()
    client.post("/api/chat", json={"channel": "main", "text": "4.1%"}).raise_for_status()
    log = client.get("/api/events?channel=main").json()
    job = router_job(meeting, rooms, agents, log, since=log[-2]["id"])
    assert job.seen[-1].startswith("you: before the post goes to #design, i need:")
    assert job.new == ["person: 4.1%"]


@pytest.mark.parametrize("n", [8, 39])
def test_the_pm_waits_for_the_speaker_to_finish(n):
    from renga.design import sandbox
    assert n < sandbox.PM_BACKLOG and sandbox.BACKLOG <= n  # a run of lines that wakes the aides, not the pm
