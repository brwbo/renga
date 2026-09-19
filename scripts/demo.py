"""Plays a short meeting into the room so there is something to watch before
the agents have brains. Talks to a running server over http, the same way the
agents on modal will.

    .venv/bin/python scripts/demo.py [http://localhost:8020]
"""

import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8020"

SCRIPT = [
    ("say", "pm", "chat", None, "morning all. meeting's starting, everyone on your posts."),
    ("say", "transcript", "announce_start", None, "listening to the meet tab"),
    ("say", "transcript", "chat", None, "sam: \"i'll send the deck over to priya after this.\""),
    ("say", "notes", "chat", None, "action: sam sends the deck to priya. no deadline said."),
    ("say", "visual", "chat", None, "slide 4 says q3 revenue is up 18%, but nobody read that out."),
    ("say", "pm", "handoff", "actions", "draft sam's follow-up to priya, attach the deck."),
    ("say", "actions", "announce_start", None, "drafting the follow-up email"),
    ("say", "marketing", "chat", None, "\"we cut onboarding from a week to a day\" is a strong hook. flagging it for a short."),
    ("ask", "actions", None, None, "which deck: the q3 review or the pitch deck?", ["q3 review", "pitch deck"]),
    ("say", "marketing", "announce_done", None, "30-second video script drafted from the onboarding line"),
    ("ask", "marketing", None, None, "ok to quote sam by name in public posts?", ["yes", "no, keep it anonymous"]),
]


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=10) as client:
        for step in SCRIPT:
            if step[0] == "say":
                _, agent, kind, to, text = step
                client.post("/api/say", json={"agent_id": agent, "kind": kind, "to": to,
                                              "text": text}).raise_for_status()
            else:
                _, agent, _, _, text, options = step
                client.post("/api/questions", json={"agent_id": agent, "text": text,
                                                    "options": options}).raise_for_status()
            time.sleep(1.5)


if __name__ == "__main__":
    main()
