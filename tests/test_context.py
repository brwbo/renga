import asyncio
import os
from pathlib import Path

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from renga.design.crew import Crew, about
from renga.design.presets import PRESETS_BY_ID

DOC = "# acme\n\nwe sell rope. the audience is climbers. never say 'synergy'."
DESIGN_IDS = {m.role: f"design-{m.role}" for m in PRESETS_BY_ID["brand-campaign"].members}


# ---- the team's context doc ------------------------------------------------
def test_a_team_has_no_context_until_one_is_written(client):
    assert client.get("/api/teams/renga/context").json() == {"team": "renga", "text": ""}


def test_context_is_saved_stripped_and_overwritten(client):
    r = client.put("/api/teams/renga/context", json={"text": f"  {DOC}\n\n"})
    assert r.status_code == 200 and r.json() == {"team": "renga", "text": DOC}
    assert client.get("/api/teams/renga/context").json()["text"] == DOC
    client.put("/api/teams/renga/context", json={"text": "rope, but shorter"}).raise_for_status()
    assert client.get("/api/teams/renga/context").json()["text"] == "rope, but shorter"
    assert client.get("/api/teams/rowbo/context").json()["text"] == ""  # each team its own


def test_context_needs_a_real_team_and_a_sane_length(client):
    assert client.get("/api/teams/nobody/context").status_code == 404
    assert client.put("/api/teams/nobody/context", json={"text": "x"}).status_code == 404
    assert client.put("/api/teams/renga/context", json={"text": "x" * 50_001}).status_code == 422
    assert client.put("/api/teams/renga/context", json={"text": "x" * 50_000}).status_code == 200


def test_deleting_a_team_deletes_its_context(client):
    team = {"name": "gone", "repo": "a/gone"}
    client.post("/api/teams", json=team).raise_for_status()
    client.put("/api/teams/gone/context", json={"text": DOC}).raise_for_status()
    assert client.delete("/api/teams/gone").status_code == 204
    assert client.get("/api/teams/gone/context").status_code == 404
    client.post("/api/teams", json=team).raise_for_status()  # the same name again starts blank
    assert client.get("/api/teams/gone/context").json()["text"] == ""


def test_aurelia_is_built_in_and_reads_the_company_file(client):
    company = (Path(__file__).resolve().parents[1] / "docs/company.md").read_text().strip()
    # aurelia is a copy of renga: the same rooms and agents, ids prefixed
    rooms = {r["id"]: r for r in client.get("/api/rooms?team=aurelia").json()}
    assert [r["name"] for r in rooms.values()] == ["meeting", "design", "logfire"]
    assert rooms["aurelia-meeting"]["lead"] == "aurelia-pm"
    assert rooms["aurelia-design"]["lead"] == "aurelia-design-creative-director"
    agents = client.get("/api/agents").json()
    renga = {r["id"] for r in client.get("/api/rooms?team=renga").json()}
    mine = {a["id"]: a for a in agents if a["room"] in rooms}
    assert set(mine) == {f"aurelia-{a['id']}" for a in agents if a["room"] in renga}
    assert mine["aurelia-transcript"]["senses"] == ["captions"] and mine["aurelia-visual"]["senses"] == ["screen"]
    # its pm hands work to its own #design, and can walk in there; nobody else's
    task = client.post("/api/delegate", json={"from_agent": "aurelia-pm", "room": "aurelia-design",
                                              "text": "a launch post"}).json()
    assert task["to"] == "aurelia-design-creative-director"
    assert client.post("/api/say", json={"agent_id": "aurelia-pm", "channel": "aurelia-design",
                                         "text": "hi"}).status_code == 201
    assert client.post("/api/say", json={"agent_id": "aurelia-pm", "channel": "design",
                                         "text": "hi"}).status_code == 403
    assert client.get("/api/teams/aurelia/context").json()["text"] == company
    client.put("/api/teams/aurelia/context", json={"text": DOC}).raise_for_status()
    assert client.get("/api/teams/aurelia/context").json()["text"] == DOC  # the ui's wins
    client.put("/api/teams/aurelia/context", json={"text": ""}).raise_for_status()
    assert client.get("/api/teams/aurelia/context").json()["text"] == company  # cleared: the file
    assert client.post("/api/workflows/meeting-to-marketing/start",
                       json={"team": "aurelia"}).status_code == 409
    assert client.delete("/api/teams/aurelia").status_code == 204
    assert client.get("/api/rooms?team=aurelia").json() == []


# ---- the context reaches the agents ----------------------------------------
def heard(seen: list[str], args: dict) -> FunctionModel:
    """Answers every call with `args`, and keeps the instructions it was given."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info.instructions or "")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    return FunctionModel(reply)


def test_about_is_empty_for_a_blank_context():
    assert about("") == about("  \n ") == ""
    assert about(f"\n{DOC}\n").endswith(DOC) and "the team's context" in about(DOC)


def test_every_crew_member_reads_the_context():
    p = PRESETS_BY_ID["brand-campaign"]
    crew = Crew(p, context=DOC)
    assert all(DOC in crew._instructions(m.role) for m in p.members)
    assert DOC in crew._instructions(p.lead, lead="plan") and DOC in crew._instructions(p.lead, lead="review")
    assert "the team's context" not in Crew(p)._instructions(p.lead)


def test_the_project_manager_reads_the_context():
    from renga.design.router import Router, Target

    async def run(lines):
        return [line async for line in lines if line.kind != "thinking"]

    seen: list[str] = []
    router = Router("meeting", "pm", [Target(room="design", name="design")],
                    model=heard(seen, {"say": None, "handoffs": []}), context=DOC)
    assert asyncio.run(run(router.run([], ["priya: we need a hero"]))) == []
    assert len(seen) == 1 and DOC in seen[0]

    blank: list[str] = []
    asyncio.run(run(Router("meeting", "pm", [], model=heard(blank, {"say": None, "handoffs": []})).run([], ["hi"])))
    assert "the team's context" not in blank[0]


def test_prepare_fetches_the_rooms_team_context(client):
    from renga.design.jobs import crew_job
    from renga.design.sandbox import prepare

    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    room = next(r for r in rooms if r["id"] == "design")
    job = prepare(client, crew_job(room, agents, "a post"), room, rooms)
    assert job.context == ""
    client.put(f"/api/teams/{room['team']}/context", json={"text": DOC}).raise_for_status()
    job = prepare(client, crew_job(room, agents, "a post"), room, rooms)
    assert job.context == DOC
    assert job.watch == "logfire"  # renga's #logfire
    # a room whose team has gone: no context, and no error
    assert prepare(client, job, {**room, "team": "nobody"}, rooms).context == ""


def test_a_crew_run_from_a_job_carries_the_context_into_every_call(client):
    from renga.design.inside import stream
    from renga.design.jobs import crew_job

    rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    room = next(r for r in rooms if r["id"] == "design")
    job = crew_job(room, agents, "a post")
    job.context = DOC
    seen: list[str] = []

    async def printed():
        return [o async for o in stream(job, model=working(seen))]

    assert asyncio.run(printed())
    assert len(seen) >= 3 and all(DOC in s for s in seen)  # plan, work, review


# ---- files the agents make -------------------------------------------------
SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'


def say_done(client, files: list[dict]):
    return client.post("/api/say", json={"agent_id": "design-copywriter", "channel": "design",
                                         "kind": "announce_done", "text": "made a hero",
                                         "data": {"deliverable": "# hero", "files": files}})


def test_a_file_an_agent_makes_is_kept_and_served_sandboxed(client):
    r = say_done(client, [{"name": "hero.svg", "content": SVG}, {"name": "post.md", "content": "# hi"}])
    assert r.status_code == 201, r.text
    files = r.json()["data"]["files"]
    assert [(f["name"], f["type"], f["size"]) for f in files] == [
        ("hero.svg", "image/svg+xml", len(SVG)), ("post.md", "text/markdown", 4)]
    got = client.get(files[0]["url"])
    assert got.status_code == 200 and got.text == SVG
    assert got.headers["content-type"].startswith("image/svg+xml")
    assert got.headers["content-security-policy"].startswith("sandbox")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert client.get(files[1]["url"]).headers["content-type"].startswith("text/markdown")
    event = client.get("/api/events?channel=design").json()[-1]
    assert all("content" not in f for f in event["data"]["files"])
    assert SVG not in str(event)


def test_bad_files_are_refused(client):
    for bad in [{"name": "hero.exe", "content": "x"}, {"name": "../..svg", "content": "x"},
                {"name": ".svg", "content": "x"}, {"name": "hero.svg"},
                {"name": "big.txt", "content": "x" * 500_001}]:
        assert say_done(client, [bad]).status_code == 422, bad
    assert client.get("/api/events?channel=design").json() == []
    # names follow crew.File's rule, and one bad file keeps the rest off disk too
    for name in ["../../etc.svg", "<img src=x onerror=alert(1)>.svg", "Hero.SVG"]:
        assert say_done(client, [{"name": "ok.svg", "content": SVG}, {"name": name, "content": SVG}]).status_code == 422
    for files in ["hero.svg", ["hero.svg"], [{"name": "a.md", "content": "x"}] * 9]:
        assert say_done(client, files).status_code == 422
    assert client.get("/api/events?channel=design").json() == []
    kept = Path(os.environ["RENGA_FILES"])
    assert not kept.exists() or not any(kept.iterdir())
    for name in ["nope.svg", "..%2Fetc.svg", ".hidden.svg", "x.exe"]:
        assert client.get(f"/files/{name}").status_code == 404, name


def working(seen: list[str] | None = None) -> FunctionModel:
    """A crew that plans one graphic designer, who hands back a file, and approves it."""

    def reply(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(info.instructions or "")
        tool = info.output_tools[0]
        fields = tool.parameters_json_schema["properties"]
        if "assignments" in fields:
            args = {"say": "design has it", "assignments": [{"role": "graphic-designer", "task": "a hero"}]}
        elif "approved" in fields:
            args = {"say": "ship it", "approved": True}
        else:
            args = {"say": "here's the hero", "deliverable": "# hero",
                    "files": [{"name": "hero.svg", "content": SVG}]}
        return ModelResponse(parts=[ToolCallPart(tool.name, args)])

    return FunctionModel(reply)


def test_files_from_a_crew_run_land_in_the_room_as_links(client):
    crew = Crew(PRESETS_BY_ID["brand-campaign"], room="design", model=working(), ids=DESIGN_IDS)

    async def go():
        return [line async for line in crew.run("a hero")]

    lines = asyncio.run(go())
    done = next(line for line in lines if line.agent_id == "design-graphic-designer" and line.kind == "announce_done")
    assert done.data["files"] == [{"name": "hero.svg", "content": SVG}]
    for line in lines:
        path, body = line.request()
        assert client.post(path, json=body).status_code == 201, body
    events = client.get("/api/events?channel=design").json()
    files = [f for e in events for f in (e.get("data") or {}).get("files", [])]
    assert len(files) == 1 and set(files[0]) == {"name", "url", "type", "size"}
    assert client.get(files[0]["url"]).text == SVG
