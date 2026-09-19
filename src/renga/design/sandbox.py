"""The agents' host. Every room with brains gets its own named modal sandbox,
and every piece of work is a process run inside it (inside.py): a crew
working a brief, or a project manager reading the meeting. What they say
streams back here and is posted into renga. renga stays on your machine;
only the agents run on modal.

A sandbox stays up between jobs and shuts itself down after sitting idle.
It can only reach the model's api (and logfire), nothing else. Its name
carries a hash of this package and the model, so changing the agents' code
or the model gets you a fresh sandbox instead of a stale one.

The model is RENGA_MODEL (claude by default); its provider decides which
modal secret holds the key.

    # once: the key the agents think with, claude or gemini
    modal secret create anthropic ANTHROPIC_API_KEY=...
    modal secret create gemini GEMINI_API_KEY=...   # with RENGA_MODEL=google:...

    python -m renga.design.sandbox run brand-campaign "a linkedin post about..."
    python -m renga.design.sandbox listen   # crews pick up briefs, pms read meetings
    python -m renga.design.sandbox stop     # shuts every room's sandbox down
"""

import argparse
import hashlib
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from .crew import DEFAULT_MODEL, Line
from .jobs import Job, brains, crew_job, router_job

APP = "renga-design"
IDLE = 20 * 60  # a sandbox with nothing running shuts down after this
LIFETIME = 24 * 60 * 60
LOGFIRE = ["logfire-us.pydantic.dev", "logfire-eu.pydantic.dev"]
QUIET = 15.0  # the pm reads the meeting once it goes quiet for this long...
BACKLOG = 8   # ...or once this many lines are waiting, whichever comes first

# provider: (the modal secret with its key, the one api host it may reach)
PROVIDERS = {
    "anthropic": ("anthropic", "api.anthropic.com"),
    "google": ("gemini", "generativelanguage.googleapis.com"),
}


def model() -> str:
    return os.environ.get("RENGA_MODEL", DEFAULT_MODEL)


def provider(name: str) -> tuple[str, str]:
    """The secret and host for a model like `google:gemini-3.1-pro-preview`."""
    prefix = name.partition(":")[0]
    if prefix not in PROVIDERS:
        raise SystemExit(f"renga's sandboxes know {', '.join(PROVIDERS)} models, not {name!r}")
    return PROVIDERS[prefix]


def version() -> str:
    """A hash of the design package and the model, so new code or a new
    model means a new sandbox."""
    h = hashlib.sha256(model().encode())
    for f in sorted(Path(__file__).parent.glob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:8]


def sandbox(room: str):
    """The room's sandbox: the running one, or a new one."""
    import modal

    name = f"renga-{room[:40]}-{version()}"
    try:
        return modal.Sandbox.from_name(APP, name)
    except modal.exception.NotFoundError:
        pass
    secret, host = provider(model())
    image = (modal.Image.debian_slim(python_version="3.12")
             .pip_install("pydantic>=2.9", "pydantic-ai-slim[anthropic,google]", "logfire>=5.1")
             .add_local_python_source("renga", copy=True))
    try:
        return modal.Sandbox.create(
            "sleep", "infinity", name=name, tags={"room": room, "model": model()},
            app=modal.App.lookup(APP, create_if_missing=True), image=image,
            secrets=[modal.Secret.from_name(secret)], env={"RENGA_MODEL": model()},
            workdir="/root", timeout=LIFETIME, idle_timeout=IDLE,
            outbound_domain_allowlist=[host, *LOGFIRE])
    except modal.exception.AlreadyExistsError:  # another job made it first
        return modal.Sandbox.from_name(APP, name)


def pump(out: Iterable[str], post: Callable[[str, dict], object]) -> int:
    """Post every line the agents print into renga. Returns how many."""
    n = 0
    for raw in out:
        if raw.strip():
            post(*Line.model_validate_json(raw).request())
            n += 1
    return n


def run_job(renga: str, job: Job) -> None:
    """Run one job in its room's sandbox and post what it says into renga."""
    import httpx

    proc = sandbox(job.room).exec("python", "-m", "renga.design.inside", bufsize=1)
    proc.stdin.write(job.model_dump_json())
    proc.stdin.write_eof()
    proc.stdin.drain()
    with httpx.Client(base_url=renga, timeout=30) as client:
        def post(path: str, body: dict) -> None:
            r = client.post(path, json=body)
            if r.is_error:
                print(f"renga said {r.status_code} to {body.get('agent_id') or body.get('from_agent')}: {r.text}")
        pump(proc.stdout, post)
    if proc.wait():
        print(f"#{job.room} stopped with an error:\n{proc.stderr.read()}")


def run(renga: str, room_id: str, brief: str) -> None:
    """Hand one brief straight to a room's crew."""
    import httpx

    with httpx.Client(base_url=renga, timeout=30) as client:
        rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
    room = next((r for r in rooms if r["id"] == room_id), None)
    if not room or brains(room, agents) != "crew":
        crews = sorted(r["id"] for r in rooms if brains(r, agents) == "crew")
        raise SystemExit(f"{room_id!r} isn't a room with a crew. try one of: {', '.join(crews)}")
    run_job(renga, crew_job(room, agents, brief))


class Meeting:
    """One meeting room the project manager is reading."""

    def __init__(self, since: int):
        self.routed = since  # everything up to here has been read
        self.waiting = 0     # lines said since then
        self.last = 0.0      # when the last one was said
        self.busy = False


def listen(renga: str, every: float = 2.0) -> None:
    """Watch renga. A brief handed to a crew's lead from another room starts
    that crew; what's said in a meeting room wakes its project manager once
    the meeting goes quiet or enough has piled up. Nothing is replayed."""
    import httpx

    def start(job: Job, done: Callable[[], None] = lambda: None) -> None:
        def go():
            try:
                run_job(renga, job)
            except Exception as err:  # keep listening whatever one job does
                print(f"#{job.room}: {err}")
            finally:
                done()
        threading.Thread(target=go, daemon=True).start()

    meetings: dict[str, Meeting] = {}
    with httpx.Client(base_url=renga, timeout=30) as client:
        since = max((e["id"] for e in client.get("/api/events").json()), default=0)
        print(f"listening to {renga}")
        while True:
            rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
            by_id = {r["id"]: r for r in rooms}
            for e in client.get("/api/events", params={"since": since}).json():
                since = max(since, e["id"])
                room = by_id.get(e["channel"])
                if not room:
                    continue
                kind = brains(room, agents)
                if (kind == "crew" and e["kind"] == "task" and e["to"] == room["lead"]
                        and (e.get("data") or {}).get("delegated_from")):
                    print(f"#{room['name']} got a brief, its crew is on it")
                    start(crew_job(room, agents, e["text"],
                                   (e.get("data") or {}).get("traceparent", "")))
                elif kind == "router" and e["kind"] in ("chat", "answer") and e["from"] != room["lead"]:
                    m = meetings.setdefault(room["id"], Meeting(e["id"] - 1))
                    m.waiting, m.last = m.waiting + 1, time.monotonic()
            for room_id, m in meetings.items():
                quiet = time.monotonic() - m.last >= QUIET
                if m.waiting and not m.busy and (quiet or m.waiting >= BACKLOG) and room_id in by_id:
                    log = client.get("/api/events", params={"channel": room_id}).json()
                    job = router_job(by_id[room_id], rooms, agents, log, m.routed)
                    m.routed, m.waiting, m.busy = since, 0, True
                    print(f"#{by_id[room_id]['name']}: the project manager is reading {len(job.new)} lines")
                    start(job, done=lambda m=m: setattr(m, "busy", False))
            time.sleep(every)


def stop() -> None:
    import modal

    app = modal.App.lookup(APP, create_if_missing=True)
    for sb in modal.Sandbox.list(app_id=app.app_id):
        sb.terminate()
        print(f"stopped {sb.object_id} ({sb.get_tags().get('room', '?')})")


def cli() -> None:
    ap = argparse.ArgumentParser(prog="python -m renga.design.sandbox")
    ap.add_argument("--renga", default="http://localhost:8020")
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("run", help="hand one brief to a room's crew")
    one.add_argument("room")
    one.add_argument("brief")
    sub.add_parser("listen", help="run crews on briefs and project managers on meetings")
    sub.add_parser("stop", help="shut every room's sandbox down")
    args = ap.parse_args()
    if args.cmd != "stop":
        provider(model())  # fail here, not in the sandbox, on a model we can't host
    if args.cmd == "run":
        run(args.renga, args.room, args.brief)
    elif args.cmd == "listen":
        listen(args.renga)
    else:
        stop()


if __name__ == "__main__":
    cli()
