"""What runs inside a team's sandbox on modal. Reads a brief on stdin, runs
the team, and prints each Line as one line of json on stdout for the host
(sandbox.py) to post into renga.

    echo "a linkedin post" | python -m renga.design.inside brand-campaign [room]
"""

import asyncio
import sys
from collections.abc import AsyncIterator

from .crew import Crew
from .presets import PRESETS_BY_ID


async def stream(preset: str, room: str, brief: str, model=None) -> AsyncIterator[str]:
    crew = Crew(PRESETS_BY_ID[preset], room=room or None, model=model)
    async for line in crew.run(brief):
        yield line.model_dump_json()


async def main(preset: str, room: str = "") -> None:
    async for out in stream(preset, room, sys.stdin.read()):
        print(out, flush=True)


if __name__ == "__main__":
    import logfire

    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
    asyncio.run(main(*sys.argv[1:3]))
