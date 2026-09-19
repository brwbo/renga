"""Plays a short meeting into the rooms so there is something to watch before
the agents have brains. The pm hands the marketing work to the design team,
whose lead splits it up. Talks to a running server over http, the same way
the agents on modal will.

    .venv/bin/python scripts/demo.py [http://localhost:8020]
"""

import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8020"


def say(agent, text, kind="chat", to=None, channel="main"):
    return ("/api/say", {"agent_id": agent, "text": text, "kind": kind, "to": to, "channel": channel})


def ask(agent, text, options, channel="main"):
    return ("/api/questions", {"agent_id": agent, "text": text, "options": options, "channel": channel})


def delegate(team, text):
    return ("/api/delegate", {"team": team, "text": text})


SCRIPT = [
    say("pm", "morning. meeting's starting, everyone on your posts."),
    say("transcript", "listening to the meet tab", kind="announce_start"),
    say("transcript", "sam: \"i'll send the deck over to priya after this.\""),
    say("notes", "action: sam sends the deck to priya. no deadline said."),
    say("visual", "slide 4 says q3 revenue is up 18%, but nobody read that out."),
    say("transcript", "priya: \"we cut onboarding from a week to a day.\""),
    say("pm", "draft sam's follow-up to priya, attach the deck.", kind="handoff", to="actions"),
    say("actions", "drafting the follow-up email", kind="announce_start"),
    delegate("design", "priya's line \"we cut onboarding from a week to a day\" is a strong hook. "
                       "make a 30-second video and a linkedin post around it, using the 18% from slide 4."),
    say("director", "on it. video takes the script, copy takes the post, visuals the thumbnail. "
                    "brand checks all three before they go back.", channel="design"),
    say("video", "writing the script", kind="announce_start", channel="design"),
    say("copy", "first line: \"a week of onboarding, down to a day.\" building the post from there.",
        channel="design"),
    ask("actions", "which deck: the q3 review or the pitch deck?", ["q3 review", "pitch deck"]),
    say("video", "30-second script drafted: hook, 3 scenes, cta", kind="announce_done", channel="design"),
    ask("brand", "ok to quote priya by name in public posts?", ["yes", "no, keep it anonymous"],
        channel="design"),
    say("actions", "follow-up drafted, waiting on which deck", kind="announce_done"),
]


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=10) as client:
        for path, body in SCRIPT:
            client.post(path, json=body).raise_for_status()
            time.sleep(1.2)


if __name__ == "__main__":
    main()
