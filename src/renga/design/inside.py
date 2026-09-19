"""What runs inside a team's sandbox on modal. Reads a brief on stdin, runs
the team, and prints each Line as one line of json on stdout for the host
(sandbox.py) to post into renga.

The whole run is one logfire span, a child of the pm's hand-off when the
host passes its traceparent. The logfire agent reads the spans as they end
and posts each agent run into #logfire: who, how long, the tokens, errors.

    echo "a linkedin post" | python -m renga.design.inside brand-campaign [room] [traceparent]
"""

import asyncio
import sys
from collections import defaultdict
from collections.abc import AsyncIterator

import logfire
from logfire.propagate import attach_context
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import StatusCode

from .crew import Crew, Line
from .presets import PRESETS_BY_ID

ROOM = "logfire"  # the room and the agent that posts the traces


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


def _say(text: str, **data) -> str:
    return Line(agent_id=ROOM, channel=ROOM, kind="chat", text=text, data=data).model_dump_json()


def _run_line(room: str, trace_id: str, run: dict) -> str:
    who = run["role"].replace("-", " ") + ("" if run["step"] == "work" else f" ({run['step']})")
    if run["error"]:
        return _say(f"#{room}: {who} failed after {run['secs']}s: {run['error']}",
                    trace_id=trace_id, room=room, **run)
    return _say(f"#{room}: {who} took {run['secs']}s, "
                f"{run['input_tokens']:,} in / {run['output_tokens']:,} out tokens",
                trace_id=trace_id, room=room, **run)


async def stream(preset: str, room: str, brief: str, model=None,
                 traceparent: str = "") -> AsyncIterator[str]:
    crew = Crew(PRESETS_BY_ID[preset], room=room or None, model=model)
    room, runs = crew.room, []
    with attach_context({"traceparent": traceparent} if traceparent else {}), \
            logfire.span("#{room} works on a brief", room=room, team=preset) as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        yield _say(f"#{room} started on a brief", trace_id=trace_id, room=room)

        def watched() -> list[str]:
            done = WATCH.drain(trace_id)
            runs.extend(done)
            return [_run_line(room, trace_id, r) for r in done]

        try:
            async for line in crew.run(brief):
                yield line.model_dump_json()
                for out in watched():
                    yield out
        except Exception as err:
            for out in watched():
                yield out
            yield _say(f"#{room} stopped: {err}", trace_id=trace_id, room=room, error=str(err))
            raise
        tokens = sum(r["input_tokens"] + r["output_tokens"] for r in runs)
        yield _say(f"#{room} finished: {len(runs)} agent runs, {tokens:,} tokens",
                   trace_id=trace_id, room=room, runs=len(runs), tokens=tokens)


async def main(preset: str, room: str = "", traceparent: str = "") -> None:
    async for out in stream(preset, room, sys.stdin.read(), traceparent=traceparent):
        print(out, flush=True)


if __name__ == "__main__":
    logfire.configure(send_to_logfire="if-token-present", console=False,
                      additional_span_processors=[WATCH])
    logfire.instrument_pydantic_ai()
    asyncio.run(main(*sys.argv[1:4]))
