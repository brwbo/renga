def test_a_room_can_be_added_to_a_team(client):
    r = client.post("/api/teams/renga/rooms", json={"name": "#Social Media", "purpose": "posts and replies"})
    assert r.status_code == 201, r.text
    made = r.json()
    assert made == {"id": "renga-social-media", "team": "renga", "name": "social-media",
                    "purpose": "posts and replies", "lead": None}
    assert "renga-social-media" in {x["id"] for x in client.get("/api/rooms?team=renga").json()}
    first = client.get("/api/events?channel=renga-social-media").json()[0]
    assert first["kind"] == "state" and first["text"] == "#social-media is set up"
    # it starts empty, and agents join it as in any room
    joined = client.post("/api/rooms/renga-social-media/agents", json={"template": "seo-specialist"})
    assert joined.status_code == 201 and joined.json()["room"] == "renga-social-media"


def test_a_team_cant_have_two_rooms_with_one_name(client):
    assert client.post("/api/teams/renga/rooms", json={"name": "design"}).status_code == 409
    assert client.post("/api/teams/renga/rooms", json={"name": "ideas"}).status_code == 201
    assert client.post("/api/teams/renga/rooms", json={"name": "Ideas"}).status_code == 409
    assert client.post("/api/teams/rowbo/rooms", json={"name": "ideas"}).status_code == 201  # another team's fine


def test_a_room_needs_a_real_name_and_team(client):
    assert client.post("/api/teams/renga/rooms", json={"name": "!!!"}).status_code == 422
    assert client.post("/api/teams/renga/rooms", json={"name": ""}).status_code == 422
    assert client.post("/api/teams/nope/rooms", json={"name": "ideas"}).status_code == 404


def test_a_made_teams_added_rooms_go_with_it(client):
    client.post("/api/teams", json={"name": "umbra", "repo": "brwbo/umbra"}).raise_for_status()
    client.post("/api/teams/umbra/rooms", json={"name": "ops"}).raise_for_status()
    assert client.delete("/api/teams/umbra").status_code == 204
    assert client.get("/api/rooms?team=umbra").json() == []
