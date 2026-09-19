import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RENGA_DB", str(tmp_path / "test.db"))
    for name in [m for m in sys.modules if m.startswith("renga")]:
        del sys.modules[name]
    main = importlib.import_module("renga.main")
    with TestClient(main.app) as c:
        yield c


def test_every_team_has_a_lead_in_it(client):
    teams = client.get("/api/teams").json()
    agents = {a["id"]: a for a in client.get("/api/agents").json()}
    assert {t["id"] for t in teams} == {"main", "design"}
    for t in teams:
        assert agents[t["lead"]]["team"] == t["id"]
    assert "marketing" not in agents


def test_pm_delegates_to_the_design_lead(client):
    task = client.post("/api/delegate", json={"team": "design", "text": "make a video"}).json()
    assert task["channel"] == "design" and task["to"] == "director" and task["kind"] == "task"
    main = client.get("/api/events?channel=main").json()
    assert main[-1]["kind"] == "handoff" and main[-1]["to"] == "team:design"


def test_cannot_delegate_to_a_missing_team(client):
    assert client.post("/api/delegate", json={"team": "sales", "text": "x"}).status_code == 404
    assert client.post("/api/delegate", json={"team": "main", "text": "x"}).status_code == 404


def test_agents_stay_in_their_own_room(client):
    assert client.post("/api/say", json={"agent_id": "copy", "text": "hi", "channel": "main"}).status_code == 403
    assert client.post("/api/say", json={"agent_id": "copy", "text": "hi", "channel": "design"}).status_code == 201
    assert client.post("/api/say", json={"agent_id": "pm", "text": "hi", "channel": "design"}).status_code == 201


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
