"""What runs inside a room's sandbox on modal. Reads one Job (jobs.py) as
json on stdin, runs it, and prints each Line as one line of json on stdout
for the host (sandbox.py) to post into renga.

The whole job is one logfire span, a child of the hand-off when the job
carries its traceparent. With `watch` set (there's a #logfire room), the
logfire agent reads the spans as they end and posts each agent run into it:
who, how long, the tokens, errors.

    python -m renga.design.inside < job.json
"""

import asyncio
import base64
import json
import sys
from collections import defaultdict
from collections.abc import AsyncIterator

import logfire
from logfire.propagate import attach_context
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import StatusCode

from .crew import Crew, Line
from .ears import Ears
from .jobs import Job
from .notes import NoteTaker
from .router import Router
from .visualiser import Visualiser

class Watch(SpanProcessor):
    """Keeps every agent run that ends, by trace, for stream() to post."""

    def __init__(self) -> None:
        self.runs: dict[str, list[dict]] = defaultdict(list)

    def on_end(self, span: ReadableSpan) -> None:
        a = span.attributes or {}
        if a.get("gen_ai.operation.name") != "invoke_agent":
            return
        role, _, step = str(a.get("agent_name", "agent")).partition(":")
        self.runs[f"{span.context.trace_id:032x}"].append({
            "role": role, "step": step or "work", "model": a.get("model_name"),
            "secs": round((span.end_time - span.start_time) / 1e9, 1),
            "input_tokens": a.get("gen_ai.aggregated_usage.input_tokens", 0),
            "output_tokens": a.get("gen_ai.aggregated_usage.output_tokens", 0),
            "error": span.status.description if span.status.status_code == StatusCode.ERROR else None,
        })

    def drain(self, trace_id: str) -> list[dict]:
        return self.runs.pop(trace_id, [])


WATCH = Watch()


def _say(where: str, text: str, **data) -> str:
    """A line from the logfire agent into its team's #logfire room (same id)."""
    return Line(agent_id=where, channel=where, kind="chat", text=text, data=data).model_dump_json()


def _run_line(where: str, room: str, trace_id: str, run: dict) -> str:
    who = run["role"].replace("-", " ") + ("" if run["step"] == "work" else f" ({run['step']})")
    if run["error"]:
        return _say(where, f"#{room}: {who} failed after {run['secs']}s: {run['error']}",
                    trace_id=trace_id, room=room, **run)
    return _say(where, f"#{room}: {who} took {run['secs']}s, "
                f"{run['input_tokens']:,} in / {run['output_tokens']:,} out tokens",
                trace_id=trace_id, room=room, **run)


async def stream(job: Job, model=None) -> AsyncIterator[str]:
    room, runs = job.room, []
    if job.kind == "crew":
        lines = Crew(job.team, room=room, model=model, ids=job.ids, context=job.context).run(job.brief)
        doing, started = "works on a brief", "started on a brief"
    elif job.kind == "notes":
        lines = NoteTaker(room, job.me, model=model, context=job.context).run(job.notes, job.seen, job.new)
        doing, started = "takes the notes", "is taking the notes"
    elif job.kind == "hear":
        lines = Ears(room, job.me, model=model, context=job.context).run(
            base64.b64decode(job.audio), job.mime, job.seen)
        doing, started = "hears the call", "is hearing the call"
    elif job.kind == "eyes":
        lines = Visualiser(room, job.me, model=model, context=job.context).run(job.seen, job.new, job.screen)
        doing, started = "looks", "is looking"
    else:
        lines = Router(room, job.pm, job.targets, model=model, context=job.context).run(
            job.seen, job.new, job.slides)
        doing, started = "reads the meeting", "is reading the meeting"
    with attach_context({"traceparent": job.traceparent} if job.traceparent else {}), \
            logfire.span("#{room} " + doing, room=room, kind=job.kind) as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        if job.watch:
            yield _say(job.watch, f"#{room} {started}", trace_id=trace_id, room=room)

        def watched() -> list[str]:
            done = WATCH.drain(trace_id)
            runs.extend(done)
            return [_run_line(job.watch, room, trace_id, r) for r in done] if job.watch else []

        try:
            async for line in lines:
                yield line.model_dump_json()
                for out in watched():
                    yield out
        except Exception as err:
            for out in watched():
                yield out
            if job.watch:
                yield _say(job.watch, f"#{room} stopped: {err}", trace_id=trace_id, room=room, error=str(err))
            raise
        for out in watched():
            yield out
        if not job.watch:
            return
        tokens = sum(r["input_tokens"] + r["output_tokens"] for r in runs)
        yield _say(job.watch, f"#{room} finished: {len(runs)} agent runs, {tokens:,} tokens",
                   trace_id=trace_id, room=room, runs=len(runs), tokens=tokens)


async def main() -> None:
    async for out in stream(Job.model_validate_json(sys.stdin.read())):
        print(out, flush=True)


async def serve(read=None, write=None, model=None) -> None:
    """Stay up and take jobs as they come: one `{"id", "job"}` per line on
    stdin, run side by side, and every line out tagged with its job's id,
    then `{"id", "done"}` when it ends. For work that comes every few
    seconds (the call's audio): a new process per job costs more than the
    work, a model call away."""
    read = read or (lambda: sys.stdin.readline())
    write = write or (lambda text: print(text, flush=True))
    loop = asyncio.get_running_loop()
    running: set[asyncio.Task] = set()

    async def one(jid: str, job: Job) -> None:
        try:
            async for out in stream(job, model=model):
                write(json.dumps({"id": jid, "line": out}))
            write(json.dumps({"id": jid, "done": True}))
        except Exception as err:  # one job failing doesn't stop the others
            write(json.dumps({"id": jid, "done": True, "error": str(err)}))

    while raw := await loop.run_in_executor(None, read):
        if not raw.strip():
            continue
        msg = json.loads(raw)
        task = asyncio.create_task(one(msg["id"], Job.model_validate(msg["job"])))
        running.add(task)
        task.add_done_callback(running.discard)
    await asyncio.gather(*running)


if __name__ == "__main__":
    logfire.configure(send_to_logfire="if-token-present", console=False,
                      additional_span_processors=[WATCH])
    logfire.instrument_pydantic_ai()
    asyncio.run(serve() if "--serve" in sys.argv else main())
