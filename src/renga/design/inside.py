"""What runs inside a room's sandbox on modal. Reads one Job (jobs.py) as
json on stdin, runs it, and prints each Line as one line of json on stdout
for the host (sandbox.py) to post into renga.

    python -m renga.design.inside < job.json
"""

import asyncio
import sys
from collections.abc import AsyncIterator

from .crew import Crew
from .jobs import Job
from .router import Router


async def stream(job: Job, model=None) -> AsyncIterator[str]:
    if job.kind == "crew":
        lines = Crew(job.team, room=job.room, model=model, ids=job.ids).run(job.brief)
    else:
        lines = Router(job.room, job.pm, job.targets, model=model).run(job.seen, job.new)
    async for line in lines:
        yield line.model_dump_json()


async def main() -> None:
    async for out in stream(Job.model_validate_json(sys.stdin.read())):
        print(out, flush=True)


if __name__ == "__main__":
    import logfire

    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
    asyncio.run(main())
