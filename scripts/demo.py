"""Plays a short meeting into the rooms so there is something to watch before
the agents have brains. The pm hands the marketing work to the brand campaign
team, whose creative director splits it up. Talks to a running server over
http, the same way the agents on modal do. (The design teams have real brains:
with `python -m renga.design.sandbox listen` running, the brief below starts
the real brand campaign team in its modal sandbox.)

    .venv/bin/python scripts/demo.py [http://localhost:8020]
"""

import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8020"
BC = "brand-campaign"
CD = f"{BC}-creative-director"


def say(agent, text, kind="chat", to=None, channel="main"):
    return ("/api/say", {"agent_id": agent, "text": text, "kind": kind, "to": to, "channel": channel})


def ask(agent, text, options, channel="main"):
    return ("/api/questions", {"agent_id": agent, "text": text, "options": options, "channel": channel})


def delegate(room, text):
    return ("/api/delegate", {"room": room, "text": text})


SCRIPT = [
    say("pm", "morning. meeting's starting, everyone on your posts."),
    say("transcript", "listening to the meet tab", kind="announce_start"),
    say("transcript", "sam: \"i'll send the deck over to priya after this.\""),
    say("notes", "action: sam sends the deck to priya. no deadline said."),
    say("visual", "slide 4 says q3 revenue is up 18%, but nobody read that out."),
    say("transcript", "priya: \"we cut onboarding from a week to a day.\""),
    say("pm", "draft sam's follow-up to priya, attach the deck.", kind="handoff", to="actions"),
    say("actions", "drafting the follow-up email", kind="announce_start"),
    delegate("brand-campaign", "priya's line \"we cut onboarding from a week to a day\" is a strong hook. "
                       "make a 30-second video and a linkedin post around it, using the 18% from slide 4."),
    say(CD, "on it. copy writes the script and the post first, then graphics takes the thumbnail "
            "and social cuts it for linkedin.", channel=BC),
    say(f"{BC}-copywriter", "writing the script", kind="announce_start", channel=BC),
    say(f"{BC}-copywriter", "first line: \"a week of onboarding, down to a day.\" building the post from there.",
        channel=BC),
    ask("actions", "which deck: the q3 review or the pitch deck?", ["q3 review", "pitch deck"]),
    say(f"{BC}-copywriter", "30-second script drafted: hook, 3 scenes, cta", kind="announce_done", channel=BC),
    ask(CD, "ok to quote priya by name in public posts?", ["yes", "no, keep it anonymous"],
        channel=BC),
    say("actions", "follow-up drafted, waiting on which deck", kind="announce_done"),
]


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=10) as client:
        for path, body in SCRIPT:
            client.post(path, json=body).raise_for_status()
            time.sleep(1.2)


if __name__ == "__main__":
    main()
