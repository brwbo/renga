"""The agents' host. Every room with brains gets its own named modal sandbox,
and every piece of work is a process run inside it (inside.py): a crew
working a brief, a listener picking actions out of the meeting, or a
project manager handing them to the teams. What they say
streams back here and is posted into renga. renga stays on your machine;
only the agents run on modal.

A sandbox stays up between jobs and shuts itself down after sitting idle.
It can only reach the model's api (and logfire), nothing else. Its name
carries a hash of this package and the model, so changing the agents' code
or the model gets you a fresh sandbox instead of a stale one.

The model is RENGA_MODEL (gemini by default); its provider decides which
modal secret holds the key.

    # once: the key the agents think with, gemini (or claude)
    modal secret create gemini GEMINI_API_KEY=...
    modal secret create anthropic ANTHROPIC_API_KEY=...   # with RENGA_MODEL=anthropic:...

    python -m renga.design.sandbox run brand-campaign "a linkedin post about..."
    python -m renga.design.sandbox listen   # crews pick up briefs, listeners and pms read meetings
    python -m renga.design.sandbox stop     # shuts every room's sandbox down
"""

import argparse
import base64
import hashlib
import json
import os
import queue
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path

from .crew import DEFAULT_MODEL, Line
from .jobs import (Job, aide, aides, brains, crew_job, eyes_job, hear_job, logfire_id, notes_job,
                   router_job)
from .visualiser import Screen

APP = "renga-design"
IDLE = 20 * 60  # a sandbox with nothing running shuts down after this
LIFETIME = 24 * 60 * 60
LOGFIRE = ["logfire-us.pydantic.dev", "logfire-eu.pydantic.dev"]
QUIET = 15.0  # the meeting is read once it goes quiet for this long...
BACKLOG = 8   # ...or once this many lines are waiting, whichever comes first
PM_BACKLOG = 40  # the pm waits for the speaker to finish: only a very long run of lines cuts in
HEAR_EVERY = 0.25  # how often the host asks renga for the call's next audio
HEAR_AT_ONCE = 3   # chunks of one room's call transcribing side by side
HEAR_IDLE = 5 * 60  # a room's worker with no audio this long is closed, so its sandbox can idle down

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


def prepare(client, job: Job, room: dict, rooms: list[dict]) -> Job:
    """What the host adds to every job: whether to post the runs into
    #logfire, and the team's context doc."""
    here = logfire_id(room["team"])
    job.watch = here if any(r["id"] == here for r in rooms) else ""
    r = client.get(f"/api/teams/{room['team']}/context")
    job.context = r.json().get("text", "") if r.is_success else ""
    return job


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
        try:
            pump(proc.stdout, post)
        finally:  # however the job ends, nobody in the room is thinking any more
            post("/api/thinking", {"channel": job.room, "on": False})
    if proc.wait():
        print(f"#{job.room} stopped with an error:\n{proc.stderr.read()}")


class Worker:
    """One long-running `inside --serve` in a room's sandbox, for jobs that
    come every few seconds: starting a process in the sandbox for each one
    cost more than the model call. Jobs go in on stdin as json lines; a
    reader thread hands each tagged line out to the job it belongs to."""

    def __init__(self, room: str):
        self.proc = sandbox(room).exec("python", "-m", "renga.design.inside", "--serve", bufsize=1)
        self.jobs: dict[str, queue.Queue] = {}
        self.alive = True
        self.used = time.monotonic()
        self._write = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            for raw in self.proc.stdout:
                if raw.strip():
                    msg = json.loads(raw)
                    if box := self.jobs.get(msg["id"]):
                        box.put(msg)
        finally:  # the process is gone: nothing still waiting will hear back
            self.alive = False
            for box in list(self.jobs.values()):
                box.put({"done": True, "error": "the sandbox's worker stopped"})

    def run(self, job: Job, timeout: float = 120) -> list[Line]:
        """Every line the job says, once it's done."""
        jid, box = uuid.uuid4().hex, queue.Queue()
        self.jobs[jid] = box
        self.used = time.monotonic()
        try:
            with self._write:
                self.proc.stdin.write(json.dumps({"id": jid, "job": job.model_dump(mode="json")}) + "\n")
                self.proc.stdin.drain()
            lines = []
            while not (msg := box.get(timeout=timeout)).get("done"):
                lines.append(Line.model_validate_json(msg["line"]))
            if msg.get("error"):
                print(f"#{job.room}: {msg['error']}")
            return lines
        finally:
            self.jobs.pop(jid, None)
            self.used = time.monotonic()

    def close(self) -> None:
        """No more jobs: the worker finishes what it has and exits."""
        with self._write:
            self.proc.stdin.write_eof()
            self.proc.stdin.drain()


class InOrder:
    """Posts each chunk's lines in the order the chunks were said, however
    their transcriptions finish, so the transcript never runs out of order."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._given = 0   # tickets handed out
        self._next = 0    # the ticket whose lines go next
        self._done: dict[int, list] = {}

    def ticket(self) -> int:
        with self._lock:
            self._given += 1
            return self._given - 1

    def finish(self, ticket: int, lines: list, post: Callable) -> None:
        """A chunk is transcribed (lines may be empty: nobody spoke, or it
        failed); post it and whatever was waiting behind it."""
        with self._lock:
            self._done[ticket] = lines
            while self._next in self._done:
                for line in self._done.pop(self._next):
                    post(*line.request())
                self._next += 1


def hearing(renga: str) -> None:
    """The call's audio, when the extension records it instead of reading
    captions: asked for every HEAR_EVERY seconds, a few chunks of a room
    transcribing at once in that room's long-running worker, and each chunk's
    lines posted in the order they were said."""
    import httpx

    if provider(model())[0] != "gemini":  # only gemini hears audio, and only its key is in the sandbox
        print(f"can't hear calls with {model()}; set RENGA_MODEL to a gemini model")
        return
    workers: dict[str, Worker] = {}
    order: dict[str, InOrder] = {}
    busy: dict[str, int] = {}  # room -> chunks in flight
    lock = threading.Lock()

    def worker(room_id: str) -> Worker:
        with lock:
            if room_id not in workers or not workers[room_id].alive:
                workers[room_id] = Worker(room_id)
            return workers[room_id]

    def transcribe(job: Job, ticket: int) -> None:
        lines: list[Line] = []
        try:
            lines = worker(job.room).run(job)
        except Exception as err:  # keep hearing whatever one chunk does
            print(f"#{job.room}: {err}")
        finally:
            with httpx.Client(base_url=renga, timeout=30) as client:
                def post(path: str, body: dict) -> None:
                    r = client.post(path, json=body)
                    if r.is_error:
                        print(f"renga said {r.status_code} to {body.get('agent_id')}: {r.text}")
                order[job.room].finish(ticket, lines, post)
            with lock:
                busy[job.room] -= 1

    with httpx.Client(base_url=renga, timeout=30) as client:
        while True:
            try:
                full = sorted(r for r, n in busy.items() if n >= HEAR_AT_ONCE)
                chunks = client.post("/api/heard/next", json={"busy": full}).json()
                if chunks:
                    rooms = {r["id"]: r for r in client.get("/api/rooms").json()}
                for chunk in chunks:
                    room = rooms.get(chunk["room"])
                    if not room:
                        continue
                    log = client.get("/api/events", params={"channel": room["id"]}).json()
                    job = prepare(client, hear_job(room, chunk["agent_id"], chunk["audio"], chunk["mime"], log),
                                  room, list(rooms.values()))
                    job.watch = ""  # a trace line every few seconds would drown #logfire
                    ticket = order.setdefault(room["id"], InOrder()).ticket()
                    with lock:
                        busy[room["id"]] = busy.get(room["id"], 0) + 1
                    threading.Thread(target=transcribe, args=(job, ticket), daemon=True).start()
            except Exception as err:  # renga restarting: try again next time
                print(f"hearing: {err}")
            with lock:  # a call that's over: let its sandbox idle down
                for room_id, w in list(workers.items()):
                    if not busy.get(room_id) and time.monotonic() - w.used > HEAR_IDLE:
                        workers.pop(room_id)
                        try:
                            w.close()
                        except Exception:
                            pass
            time.sleep(HEAR_EVERY)


def run(renga: str, room_id: str, brief: str) -> None:
    """Hand one brief straight to a room's crew."""
    import httpx

    with httpx.Client(base_url=renga, timeout=30) as client:
        rooms, agents = client.get("/api/rooms").json(), client.get("/api/agents").json()
        room = next((r for r in rooms if r["id"] == room_id), None)
        if not room or brains(room, agents) != "crew":
            crews = sorted(r["id"] for r in rooms if brains(r, agents) == "crew")
            raise SystemExit(f"{room_id!r} isn't a room with a crew. try one of: {', '.join(crews)}")
        job = prepare(client, crew_job(room, agents, brief), room, rooms)
    run_job(renga, job)


def look(client, event: dict) -> Screen:
    """The screen the extension looked at for the visualiser, with its
    screenshot, which the sandbox can't fetch from renga itself."""
    d = event.get("data") or {}
    screen = Screen(url=d.get("url", ""), title=d.get("title", ""), text=d.get("text", ""),
                    because=d.get("because", ""), slide=d.get("slide") or 0)
    if d.get("frame") and (r := client.get(d["frame"])).is_success:
        screen.image = base64.b64encode(r.content).decode()
        screen.media_type = r.headers.get("content-type", "image/jpeg").split(";")[0]
    return screen


class Meeting:
    """One meeting room an agent is reading: its project manager, its
    note-taker or its visualiser."""

    def __init__(self, since: int):
        self.routed = since  # everything up to here has been read
        self.waiting = 0     # lines said since then
        self.last = 0.0      # when the last one was said
        self.busy = False
        self.look: dict | None = None  # the visualiser's: a look at the screen to go on now
        self.asked = False  # the project manager's: the person said something, answer now


def listen(renga: str, every: float = 2.0) -> None:
    """Watch renga. A brief handed to a crew's lead from another room starts
    that crew. What's said in a meeting room (the listener's transcript) wakes
    its project manager once the meeting goes quiet or enough has piled up;
    the person talking in the chat wakes it straight away, so it answers
    them. The listener itself has no brains. The note-taker and the
    visualiser wake on the same pauses, and the visualiser straight away on
    a look at the screen. Nothing is replayed."""
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

    # the call's audio has its own, quicker loop
    threading.Thread(target=hearing, args=(renga,), daemon=True).start()

    meetings: dict[tuple[str, str], Meeting] = {}  # (room, "pm", "notes" or "eyes")

    def heard(room_id: str, who: str, event_id: int) -> None:
        m = meetings.setdefault((room_id, who), Meeting(event_id - 1))
        if event_id > m.routed:  # a line the last job already read doesn't wake the next one
            m.waiting, m.last = m.waiting + 1, time.monotonic()

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
                    job = crew_job(room, agents, e["text"], (e.get("data") or {}).get("traceparent", ""))
                    start(prepare(client, job, room, rooms))
                elif kind == "router" and e["from"] in aides(room, agents):
                    eyes = aide(room, agents, "visualiser")
                    if eyes and e["kind"] == "tool_result" and e["from"] == eyes["id"]:
                        heard(room["id"], "eyes", e["id"])
                        meetings[(room["id"], "eyes")].look = e
                elif kind == "router" and e["kind"] in ("chat", "answer") and e["from"] != room["lead"]:
                    heard(room["id"], "pm", e["id"])
                    if e["from"] == "admin":  # the person spoke: the pm answers now
                        meetings[(room["id"], "pm")].asked = True
                    for who, role in (("notes", "note-taker"), ("eyes", "visualiser")):
                        if aide(room, agents, role):
                            heard(room["id"], who, e["id"])
            for (room_id, who), m in meetings.items():
                if room_id not in by_id or not m.waiting or m.busy:
                    continue
                room = by_id[room_id]
                if who == "pm" and m.asked:
                    ready = True
                elif who == "eyes" and m.look:
                    ready = True
                else:
                    ready = (time.monotonic() - m.last >= QUIET
                             or m.waiting >= (PM_BACKLOG if who == "pm" else BACKLOG))
                if not ready:
                    continue
                log = client.get("/api/events", params={"channel": room_id}).json()
                if who in ("notes", "eyes") and not aide(room, agents, "note-taker" if who == "notes" else "visualiser"):
                    m.waiting, m.look = 0, None  # the aide has left the room
                    continue
                if who == "notes":
                    job = notes_job(room, agents, log, m.routed)
                    print(f"#{room['name']}: the note-taker is reading {len(job.new)} lines")
                elif who == "eyes":
                    job = eyes_job(room, agents, log, m.routed, look(client, m.look) if m.look else None)
                    print(f"#{room['name']}: the visualiser is " + ("looking at the screen" if m.look
                          else f"reading {len(job.new)} lines"))
                else:
                    job = router_job(room, rooms, agents, log, m.routed)
                    print(f"#{room['name']}: the project manager is reading {len(job.new)} lines")
                # the log can run ahead of `since`: whatever this job reads is read
                m.routed, m.waiting, m.asked = max([since, *(e["id"] for e in log)]), 0, False
                if not job.new and not job.screen:
                    continue
                m.look = None
                m.busy = True
                start(prepare(client, job, room, rooms), done=lambda m=m: setattr(m, "busy", False))
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
