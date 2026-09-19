from renga.outputs import approved


def done(id_, room, who, text, work, files=()):
    return {"id": id_, "ts": id_, "channel": room, "from": who, "kind": "announce_done", "text": text,
            "data": {"deliverable": work, "files": [{"name": f, "url": f"/files/{f}"} for f in files]}}


def test_only_the_version_the_lead_signed_off_is_kept():
    events = [
        {"id": 1, "ts": 1, "channel": "design", "from": "pm", "kind": "task", "text": "a linkedin post",
         "data": {"delegated_from": "main"}},
        done(2, "design", "cw", "copy", "first copy", ["copy.md"]),
        done(3, "design", "gd", "a draft", "flat card", ["draft.svg"]),
        {"id": 4, "ts": 4, "channel": "design", "from": "cd", "kind": "chat", "text": "again",
         "data": {"review": {"approved": False}}},
        done(5, "design", "gd", "the redo", "bold card", ["final.svg"]),
        done(6, "other", "x", "elsewhere", "bold card", ["wrong-room.svg"]),
        {"id": 7, "ts": 7, "channel": "design", "from": "cd", "kind": "announce_done", "text": "done",
         "data": {"deliverables": {"copywriter": "first copy", "graphic-designer": "bold card"}}},
    ]
    [s] = approved(events)
    assert (s["room"], s["lead"], s["brief"]) == ("design", "cd", "a linkedin post")
    files = {p["role"]: [f["name"] for f in p["files"]] for p in s["pieces"]}
    assert files == {"copywriter": ["copy.md"], "graphic-designer": ["final.svg"]}


def test_a_team_with_nothing_signed_off_has_an_empty_library(client):
    assert client.get("/api/teams/renga/outputs").json() == []
    assert client.get("/api/teams/nope/outputs").status_code == 404


def test_a_file_kept_in_the_event_itself_is_served_like_any_other(client):
    from renga.outputs import kept
    f = kept({"name": "ad.html", "content": "<p>hi</p>"})
    assert f["type"] == "text/html" and f["url"].startswith("/files/") and "content" not in f
    assert client.get(f["url"]).text == "<p>hi</p>"
    assert kept({"name": "ad.html", "content": "<p>hi</p>"}) == f  # the same name every time
