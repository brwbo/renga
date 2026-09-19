"""The design teams, hosted in modal sandboxes. Every team lives in its own
named sandbox, and every brief is a process run inside it (inside.py) whose
output streams back here and is posted into the team's room. renga stays on
your machine; only the agents run on modal.

A sandbox stays up between briefs and shuts itself down after sitting idle.
It can only reach the model's api (and logfire), nothing else. Its name
carries a hash of this package and the model, so changing the agents' code
or the model gets you a fresh sandbox instead of a stale one.

The model is RENGA_MODEL (claude by default); its provider decides which
modal secret holds the key.

    # once: the key the agents think with, claude or gemini
    modal secret create anthropic ANTHROPIC_API_KEY=...
    modal secret create gemini GEMINI_API_KEY=...   # with RENGA_MODEL=google:...

    python -m renga.design.sandbox run brand-campaign "a linkedin post about..."
    python -m renga.design.sandbox listen   # picks up whatever the pm delegates
    python -m renga.design.sandbox stop     # shuts every team's sandbox down
"""

import argparse
import hashlib
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from .crew import DEFAULT_MODEL, Line
from .presets import PRESETS_BY_ID, agent_id

APP = "renga-design"
IDLE = 20 * 60  # a sandbox with nothing running shuts down after this
LIFETIME = 24 * 60 * 60
LOGFIRE = ["logfire-us.pydantic.dev", "logfire-eu.pydantic.dev"]

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


def sandbox(team: str):
    """The team's sandbox: the running one, or a new one."""
    import modal

    name = f"renga-{team}-{version()}"
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
            "sleep", "infinity", name=name, tags={"team": team, "model": model()},
            app=modal.App.lookup(APP, create_if_missing=True), image=image,
            secrets=[modal.Secret.from_name(secret)], env={"RENGA_MODEL": model()},
            workdir="/root", timeout=LIFETIME, idle_timeout=IDLE,
            outbound_domain_allowlist=[host, *LOGFIRE])
    except modal.exception.AlreadyExistsError:  # another brief made it first
        return modal.Sandbox.from_name(APP, name)


def pump(out: Iterable[str], post: Callable[[str, dict], object]) -> int:
    """Post every line the team prints into renga. Returns how many."""
    n = 0
    for raw in out:
        if raw.strip():
            post(*Line.model_validate_json(raw).request())
            n += 1
    return n


def run(renga: str, team: str, brief: str, room: str = "") -> None:
    """Run one brief in the team's sandbox and post what it says into renga."""
    import httpx

    proc = sandbox(team).exec("python", "-m", "renga.design.inside", team, room, bufsize=1)
    proc.stdin.write(brief)
    proc.stdin.write_eof()
    proc.stdin.drain()
    with httpx.Client(base_url=renga, timeout=30) as client:
        def post(path: str, body: dict) -> None:
            r = client.post(path, json=body)
            if r.is_error:
                print(f"renga said {r.status_code} to {body['agent_id']}: {r.text}")
        pump(proc.stdout, post)
    if proc.wait():
        print(f"#{room or team} stopped with an error:\n{proc.stderr.read()}")


def listen(renga: str, every: float = 2.0) -> None:
    """Watch renga for briefs the pm hands to a team's lead, and run each in
    that team's sandbox. Only new briefs: nothing is replayed."""
    import httpx

    leads = {p.id: agent_id(p.id, p.lead) for p in PRESETS_BY_ID.values()}
    with httpx.Client(base_url=renga, timeout=30) as client:
        since = max((e["id"] for e in client.get("/api/events").json()), default=0)
        print(f"listening to {renga} for briefs to: {', '.join(leads)}")
        while True:
            for e in client.get("/api/events", params={"since": since}).json():
                since = max(since, e["id"])
                if e["kind"] == "task" and e["from"] == "pm" and leads.get(e["channel"]) == e["to"]:
                    print(f"#{e['channel']} got a brief, running it in the team's sandbox")
                    threading.Thread(target=run, daemon=True,
                                     args=(renga, e["channel"], e["text"])).start()
            time.sleep(every)


def stop() -> None:
    import modal

    app = modal.App.lookup(APP, create_if_missing=True)
    for sb in modal.Sandbox.list(app_id=app.app_id):
        sb.terminate()
        print(f"stopped {sb.object_id} ({sb.get_tags().get('team', '?')})")


def cli() -> None:
    ap = argparse.ArgumentParser(prog="python -m renga.design.sandbox")
    ap.add_argument("--renga", default="http://localhost:8020")
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("run", help="run one brief with one team")
    one.add_argument("team", choices=sorted(PRESETS_BY_ID))
    one.add_argument("brief")
    sub.add_parser("listen", help="run whatever the pm delegates to a team")
    sub.add_parser("stop", help="shut every team's sandbox down")
    args = ap.parse_args()
    if args.cmd != "stop":
        provider(model())  # fail here, not in the sandbox, on a model we can't host
    if args.cmd == "run":
        run(args.renga, args.team, args.brief)
    elif args.cmd == "listen":
        listen(args.renga)
    else:
        stop()


if __name__ == "__main__":
    cli()
