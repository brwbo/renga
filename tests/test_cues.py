import base64

from renga.cues import cue

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nnot really").decode()


def test_showing_something_is_a_cue():
    for line in ["sam: as you can see, churn is down", "priya: if you look at the second column",
                 "sam: let me share my screen", "can everyone see this?", "ok, next slide",
                 "here's the dashboard", "take a look at the numbers", "you can see here it dips"]:
        assert cue(line), line
    for line in ["sam: see you friday", "priya: i'll look into it", "let's circle back",
                 "we need a launch post", "can you hear me?"]:
        assert cue(line) is None, line


def say(client, agent, text, channel="main"):
    r = client.post("/api/say", json={"agent_id": agent, "channel": channel, "text": text})
    r.raise_for_status()
    return r.json()


def test_a_cue_on_the_call_asks_the_screen_agent_to_look(client):
    said = say(client, "transcript", "sam: as you can see, churn is down")
    assert said["look"] == {"agent_id": "visual", "room": "main", "because": "as you can see"}
    assert "look" not in client.get("/api/events?channel=main").json()[-1]  # not in the log
    # once every 20 seconds per room, so a walkthrough isn't a screenshot a sentence
    assert "look" not in say(client, "transcript", "sam: and if you look here")
    # only what's heard on the call counts, and only lines that show something
    assert "look" not in say(client, "pm", "as you can see, we're on track")
    assert "look" not in say(client, "transcript", "sam: see you friday")


def test_a_team_without_a_screen_agent_doesnt_look(client):
    client.post("/api/teams", json={"name": "umbra", "repo": "brwbo/umbra",
                                    "senses": ["captions"]}).raise_for_status()
    assert "look" not in say(client, "umbra-transcript", "as you can see", channel="umbra-general")


def test_the_look_says_why_it_looked(client):
    r = client.post("/api/screen", json={"agent_id": "visual", "url": "https://meet.google.com/abc",
                                         "title": "the call", "image": PNG, "because": "as you can see"})
    r.raise_for_status()
    e = r.json()
    assert e["text"] == 'looked at the screen, because someone said "as you can see"'
    assert e["data"]["because"] == "as you can see" and e["data"]["frame"].startswith("/frames/")
