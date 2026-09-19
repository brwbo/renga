import asyncio

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from renga.design.inside import stream
from renga.design.jobs import brains, crew_job, listener_job, listener_of, router_job
from renga.design.sandbox import pump


def test_the_library_has_every_agent_and_workflow(client):
    lib = client.get("/api/library").json()
    groups = {}
    for a in lib["agents"]:
        groups.setdefault(a["group"], []).append(a["id"])
    assert groups["meeting"] == ["listener", "project-manager", "note-taker", "visualiser"]
    assert len(groups["design"]) + len(groups["marketing"]) == 16
    assert next(a for a in lib["agents"] if a["id"] == "listener")["senses"] == ["captions"]
    ids = [w["id"] for w in lib["workflows"]]
    assert ids[0] == "meeting-to-marketing" and "brand-campaign" in ids and len(ids) == 8
    meeting = lib["workflows"][0]
    assert [r["name"] for r in meeting["rooms"]] == ["meeting", "marketing"]


def test_add_a_library_agent_to_a_room(client):
    r = client.post("/api/rooms/rowbo-general/agents", json={"template": "listener"})
    assert r.status_code == 201
    a = r.json()
    assert a["id"] == "rowbo-listener" and a["template"] == "listener" and a["senses"] == ["captions"]
    named = client.post("/api/rooms/rowbo-general/agents", json={"template": "copywriter", "name": "ada"})
    assert named.json()["name"] == "ada" and named.json()["template"] == "copywriter"
    assert client.post("/api/rooms/rowbo-general/agents", json={"template": "listener"}).status_code == 409
    assert client.post("/api/rooms/rowbo-general/agents", json={"template": "plumber"}).status_code == 422
    assert client.post("/api/rooms/rowbo-general/agents", json={}).status_code == 422


def start_meeting(client, team="rowbo"):
    r = client.post("/api/workflows/meeting-to-marketing/start", json={"team": team})
    assert r.status_code == 201, r.text
    return r.json()


def test_starting_a_workflow_sets_up_its_rooms(client):
    out = start_meeting(client)
    assert [r["id"] for r in out["rooms"]] == ["rowbo-meeting", "rowbo-marketing"]
    rooms = {r["id"]: r for r in client.get("/api/rooms?team=rowbo").json()}
    assert rooms["rowbo-meeting"]["lead"] == "rowbo-meeting-project-manager"
    assert rooms["rowbo-marketing"]["lead"] == "rowbo-marketing-marketing-strategist"
    agents = client.get("/api/agents").json()
    assert brains(rooms["rowbo-meeting"], agents) == "router"
    assert brains(rooms["rowbo-marketing"], agents) == "crew"
    assert brains(rooms["rowbo-general"], agents) is None
    assert client.get("/api/events?channel=rowbo-marketing").json()[0]["kind"] == "state"
    assert client.post("/api/workflows/meeting-to-marketing/start", json={"team": "rowbo"}).status_code == 409
    assert client.post("/api/workflows/nope/start", json={"team": "rowbo"}).status_code == 404
    assert client.post("/api/workflows/meeting-to-marketing/start", json={"team": "nope"}).status_code == 404
    client.delete("/api/teams/rowbo")
    assert client.get("/api/rooms?team=rowbo").json() == []


def test_a_workflow_wont_make_a_second_room_with_the_same_name(client):
    r = client.post("/api/workflows/meeting-to-marketing/start", json={"team": "renga"})
    assert r.status_code == 409 and "#meeting" in r.json()["detail"]  # renga has one already
    assert not [x for x in client.get("/api/rooms?team=renga").json() if x["id"].startswith("renga-")]


def test_only_a_lead_hands_work_to_its_own_team(client):
    start_meeting(client)
    pm = "rowbo-meeting-project-manager"
    ok = client.post("/api/delegate", json={"from_agent": pm, "room": "rowbo-marketing", "text": "a hero image"})
    assert ok.status_code == 201
    assert ok.json()["to"] == "rowbo-marketing-marketing-strategist"
    assert ok.json()["data"]["delegated_from"] == "rowbo-meeting"
    listener = "rowbo-meeting-listener"
    assert client.post("/api/delegate", json={"from_agent": listener, "room": "rowbo-marketing",
                                              "text": "x"}).status_code == 403
    assert client.post("/api/delegate", json={"from_agent": pm, "room": "design",
                                              "text": "x"}).status_code == 404
    assert client.post("/api/delegate", json={"room": "design", "text": "x"}).status_code == 201


# ---- the connector, end to end, with a scripted model ----------------------
def scripted(reply_as: dict):
    """The listener hears the hero image is needed; the project manager sends
    it to design; design's creative director gives it to the graphic designer,
    then approves it."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        fields = tool.parameters_json_schema["properties"]
        if "actions" in fields:
            args = {"actions": [{"what": "make a hero image for the launch page", "who": "sam",
                                 "due": "friday", "why": "priya wants it bold"}]}
        elif "handoffs" in fields:
            args = {"say": "sent the hero image to design", "handoffs": [
                {"room": "rowbo-marketing", "brief": "a hero image for the launch page, bold, by friday"}]}
        elif "assignments" in fields:
            args = {"say": "graphics has this", "assignments": [
                {"role": "graphic-designer", "task": "make the hero image"}]}
        elif "approved" in fields:
            args = {"say": "ship it", "approved": True}
        else:
            args = {"say": "hero drafted", "deliverable": "# hero\n\na bold image"}
        reply_as.setdefault("calls", []).append(next(iter(fields)))
        return ModelResponse(parts=[ToolCallPart(tool.name, args)])

    return FunctionModel(reply)


def run_job(client, job, model):
    async def printed():
        return [o async for o in stream(job, model=model)]
    return pump(asyncio.run(printed()), lambda path, body: client.post(path, json=body).raise_for_status())


def test_the_meeting_reaches_the_design_team(client):
    start_meeting(client)
    for text in ["sam: we need a hero image for the launch page", "priya: bold, and by friday"]:
        client.post("/api/say", json={"agent_id": "rowbo-meeting-listener", "channel": "rowbo-meeting",
                                      "text": text}).raise_for_status()
    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    meeting = next(r for r in rooms if r["id"] == "rowbo-meeting")
    log = client.get("/api/events?channel=rowbo-meeting").json()
    job = router_job(meeting, rooms, agents, log, since=log[0]["id"])  # the set-up line is old news
    assert [t.room for t in job.targets] == ["rowbo-marketing"]
    assert job.new == ["listener: sam: we need a hero image for the launch page",
                       "listener: priya: bold, and by friday"]

    calls = {}
    run_job(client, job, scripted(calls))
    said = client.get("/api/events?channel=rowbo-meeting").json()
    assert [e["kind"] for e in said[-2:]] == ["chat", "handoff"]
    brief = client.get("/api/events?channel=rowbo-marketing").json()[-1]
    assert brief["kind"] == "task" and brief["to"] == "rowbo-marketing-marketing-strategist"

    design = next(r for r in rooms if r["id"] == "rowbo-marketing")
    run_job(client, crew_job(design, agents, brief["text"]), scripted(calls))
    done = client.get("/api/events?channel=rowbo-marketing").json()[-1]
    assert done["from"] == "rowbo-marketing-marketing-strategist" and done["kind"] == "announce_done"
    assert set(done["data"]["deliverables"]) == {"graphic-designer"}
    assert calls["calls"] == ["say", "say", "say", "say"]  # routing, plan, work, review


def test_the_listener_sends_the_pm_the_actions_it_hears(client):
    start_meeting(client)
    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    meeting = next(r for r in rooms if r["id"] == "rowbo-meeting")
    assert listener_of(meeting, agents)["id"] == "rowbo-meeting-listener"
    assert listener_of(next(r for r in rooms if r["id"] == "rowbo-marketing"), agents) is None
    for text in ["sam: we need a hero image for the launch page", "priya: bold, and by friday"]:
        client.post("/api/say", json={"agent_id": "rowbo-meeting-listener", "channel": "rowbo-meeting",
                                      "text": text}).raise_for_status()
    log = client.get("/api/events?channel=rowbo-meeting").json()
    job = listener_job(meeting, agents, log, since=log[0]["id"])
    assert job.listener == "rowbo-meeting-listener" and job.pm == "rowbo-meeting-project-manager"
    assert job.new == ["listener: sam: we need a hero image for the launch page",
                       "listener: priya: bold, and by friday"]

    calls = {}
    run_job(client, job, scripted(calls))
    action = client.get("/api/events?channel=rowbo-meeting").json()[-1]
    assert action["kind"] == "task" and action["to"] == "rowbo-meeting-project-manager"
    assert action["text"] == "action: make a hero image for the launch page (for sam, by friday). priya wants it bold"
    assert action["data"]["action"]["due"] == "friday"

    # the listener won't send it again, and the project manager acts on it
    log = client.get("/api/events?channel=rowbo-meeting").json()
    again = listener_job(meeting, agents, log, since=action["id"])
    assert again.new == [] and again.seen[-1].endswith("[sent]")
    routed = router_job(meeting, rooms, agents, log, since=action["id"] - 1)
    assert routed.new == [f"listener: {action['text']}"]
    run_job(client, routed, scripted(calls))
    assert client.get("/api/events?channel=rowbo-marketing").json()[-1]["kind"] == "task"


def test_the_built_in_transcript_is_a_listener(client):
    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    assert listener_of(next(r for r in rooms if r["id"] == "main"), agents)["id"] == "transcript"


def test_the_built_in_meeting_routes_to_the_design_rooms(client):
    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    meeting = next(r for r in rooms if r["id"] == "main")
    assert brains(meeting, agents) == "router"
    client.post("/api/chat", json={"channel": "main", "text": "we need a launch post"}).raise_for_status()
    job = router_job(meeting, rooms, agents, client.get("/api/events?channel=main").json(), since=0)
    assert job.pm == "pm" and job.new == ["admin: we need a launch post"]
    assert {t.room for t in job.targets} == {"design"}  # #logfire has no crew to hand work to
