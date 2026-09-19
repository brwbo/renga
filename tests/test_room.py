import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RENGA_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("RENGA_FRAMES", str(tmp_path / "frames"))
    for name in [m for m in sys.modules if m.startswith("renga")]:
        del sys.modules[name]
    main = importlib.import_module("renga.main")
    with TestClient(main.app) as c:
        yield c


def test_every_team_has_a_repo_and_rooms(client):
    teams = client.get("/api/teams").json()
    rooms = client.get("/api/rooms").json()
    assert all("/" in t["repo"] for t in teams)
    for t in teams:
        assert any(r["team"] == t["id"] for r in rooms)
    assert {r["id"] for r in client.get("/api/rooms?team=renga").json()} == {"main", "design"}


def test_every_lead_sits_in_their_room(client):
    agents = {a["id"]: a for a in client.get("/api/agents").json()}
    for r in client.get("/api/rooms").json():
        if r["lead"]:
            assert agents[r["lead"]]["room"] == r["id"]


def test_pm_delegates_to_the_design_lead(client):
    task = client.post("/api/delegate", json={"room": "design", "text": "make a video"}).json()
    assert task["channel"] == "design" and task["to"] == "director" and task["kind"] == "task"
    main = client.get("/api/events?channel=main").json()
    assert main[-1]["kind"] == "handoff" and main[-1]["to"] == "room:design"


def test_cannot_delegate_outside_the_team(client):
    assert client.post("/api/delegate", json={"room": "sales", "text": "x"}).status_code == 404
    assert client.post("/api/delegate", json={"room": "main", "text": "x"}).status_code == 404
    assert client.post("/api/delegate", json={"room": "rowbo-general", "text": "x"}).status_code == 404


def test_agents_stay_in_their_own_room(client):
    assert client.post("/api/say", json={"agent_id": "copy", "text": "hi", "channel": "main"}).status_code == 403
    assert client.post("/api/say", json={"agent_id": "copy", "text": "hi", "channel": "design"}).status_code == 201
    assert client.post("/api/say", json={"agent_id": "pm", "text": "hi", "channel": "design"}).status_code == 201
    assert client.post("/api/say", json={"agent_id": "pm", "text": "hi", "channel": "rowbo-general"}).status_code == 403


def test_chat_lands_in_the_log(client):
    client.post("/api/chat", json={"text": "hello room"}).raise_for_status()
    events = client.get("/api/events").json()
    assert events[-1]["from"] == "admin" and events[-1]["text"] == "hello room"


def test_agent_can_speak_but_strangers_cannot(client):
    ok = client.post("/api/say", json={"agent_id": "notes", "text": "action: send deck"})
    assert ok.status_code == 201
    assert client.post("/api/say", json={"agent_id": "nobody", "text": "hi"}).status_code == 404


def test_unknown_kind_is_rejected(client):
    r = client.post("/api/say", json={"agent_id": "notes", "kind": "gossip", "text": "x"})
    assert r.status_code == 422


def test_question_answer_round_trip(client):
    q = client.post("/api/questions", json={"agent_id": "actions", "text": "which deck?",
                                            "options": ["q3", "pitch"]}).json()
    assert [o["id"] for o in client.get("/api/questions").json()] == [q["id"]]
    r = client.post(f"/api/questions/{q['id']}/answer", json={"value": "q3"})
    assert r.json()["answered"] and r.json()["answer"] == "q3"
    assert client.get("/api/questions").json() == []
    assert client.post(f"/api/questions/{q['id']}/answer", json={"value": "pitch"}).status_code == 409
    kinds = [e["kind"] for e in client.get("/api/events").json()]
    assert kinds[-2:] == ["question", "answer"]


def test_page_is_served(client):
    assert "renga" in client.get("/").text
    assert client.get("/app.js").status_code == 200


def test_create_a_team_with_rooms_and_a_screen_reader(client):
    r = client.post("/api/teams", json={"name": "Umbra", "repo": "https://github.com/brwbo/umbra.git",
                                        "rooms": ["general", "#research"], "senses": ["screen"]})
    assert r.status_code == 201
    assert r.json()["team"]["repo"] == "brwbo/umbra"
    rooms = client.get("/api/rooms?team=umbra").json()
    assert [x["id"] for x in rooms] == ["umbra-general", "umbra-research"]
    agents = {a["id"]: a for a in client.get("/api/agents").json()}
    assert agents["umbra-visual"]["senses"] == ["screen"] and agents["umbra-visual"]["room"] == "umbra-general"
    assert "umbra-transcript" not in agents
    assert client.post("/api/chat", json={"text": "hi", "channel": "umbra-research"}).status_code == 201


def test_team_names_and_repos_are_checked(client):
    ok = {"name": "one", "repo": "brwbo/one"}
    assert client.post("/api/teams", json=ok).status_code == 201
    assert client.post("/api/teams", json=ok).status_code == 409
    assert client.post("/api/teams", json={"name": "renga", "repo": "a/b"}).status_code == 409
    assert client.post("/api/teams", json={"name": "two", "repo": "not a repo"}).status_code == 422
    assert client.post("/api/teams", json={"name": "two", "repo": "a/b", "rooms": ["x", "X"]}).status_code == 422


PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def test_only_a_screen_reader_can_send_the_screen(client):
    shot = {"url": "https://example.com", "title": "example", "text": "hello", "image": PNG}
    assert client.post("/api/screen", json={"agent_id": "notes", **shot}).status_code == 403
    event = client.post("/api/screen", json={"agent_id": "visual", **shot}).json()
    assert event["channel"] == "main" and event["kind"] == "tool_result"
    assert client.get(event["data"]["frame"]).status_code == 200
    bad = {**shot, "image": "data:text/html;base64,PGI+"}
    assert client.post("/api/screen", json={"agent_id": "visual", **bad}).status_code == 422


def test_add_an_agent_to_a_room(client):
    r = client.post("/api/rooms/rowbo-general/agents",
                    json={"name": "SEO", "role": "keeps the site findable", "senses": ["screen"]})
    assert r.status_code == 201
    a = r.json()
    assert a["id"] == "rowbo-seo" and a["room"] == "rowbo-general" and a["initials"] == "se"
    assert "rowbo-seo" in {x["id"] for x in client.get("/api/agents").json()}
    assert client.get("/api/events?channel=rowbo-general").json()[-1]["kind"] == "agent_joined"
    shot = {"agent_id": "rowbo-seo", "url": "https://rowbo.ai", "title": "rowbo"}
    assert client.post("/api/screen", json=shot).status_code == 201


def test_agent_names_are_unique_in_a_team(client):
    body = {"name": "seo", "role": "x"}
    assert client.post("/api/rooms/rowbo-general/agents", json=body).status_code == 201
    assert client.post("/api/rooms/rowbo-general/agents", json=body).status_code == 409
    assert client.post("/api/rooms/main/agents", json={"name": "notes", "role": "x"}).status_code == 409
    assert client.post("/api/rooms/nowhere/agents", json=body).status_code == 404


def test_delete_a_made_team_and_its_agents(client):
    client.post("/api/teams", json={"name": "gone", "repo": "a/gone", "senses": ["screen"]}).raise_for_status()
    client.post("/api/rooms/gone-general/agents", json={"name": "extra", "role": "x"}).raise_for_status()
    assert client.delete("/api/teams/gone").status_code == 204
    assert "gone" not in {t["id"] for t in client.get("/api/teams").json()}
    assert not [a for a in client.get("/api/agents").json() if a["id"].startswith("gone-")]
    assert client.delete("/api/teams/gone").status_code == 404
    # the name is free again
    assert client.post("/api/teams", json={"name": "gone", "repo": "a/gone"}).status_code == 201


def test_delete_a_built_in_team_and_agent(client):
    assert client.delete("/api/teams/rowbo").status_code == 204
    assert "rowbo-general" not in {r["id"] for r in client.get("/api/rooms").json()}
    assert client.delete("/api/agents/notes").status_code == 204
    assert "notes" not in {a["id"] for a in client.get("/api/agents").json()}
    assert client.get("/api/events?channel=main").json()[-1]["kind"] == "agent_left"
    assert client.post("/api/say", json={"agent_id": "notes", "text": "hi"}).status_code == 404


def test_delete_an_added_agent(client):
    client.post("/api/rooms/main/agents", json={"name": "scout", "role": "x"}).raise_for_status()
    assert client.delete("/api/agents/renga-scout").status_code == 204
    assert client.delete("/api/agents/renga-scout").status_code == 404


def test_extension_zip_points_at_this_server(client):
    import io
    import json
    import zipfile
    r = client.get("/api/extension.zip")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(z.read("renga/manifest.json"))
    assert "http://testserver/*" in manifest["host_permissions"]
    assert "const SERVER = 'http://testserver'" in z.read("renga/panel.js").decode()
