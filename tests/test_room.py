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


def test_roster_has_a_lead_and_valid_sprites(client):
    agents = client.get("/api/agents").json()
    assert [a["id"] for a in agents if a["lead"]] == ["pm"]
    assert all("skin" in a["sprite"] for a in agents)


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


def test_page_and_sprites_are_served(client):
    assert "renga" in client.get("/").text
    assert client.get("/sprites/sprites.js").status_code == 200
    assert client.get("/fonts/KenneyMini.ttf").status_code == 200
