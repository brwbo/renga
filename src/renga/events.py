"""The shape of one line in the room: `text` is the plain english people
read, `data` is the typed payload agents act on.
Every message, question, hand-off and status line is one of these."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal[
    "chat",
    "announce_start",
    "announce_done",
    "handoff",
    "task",
    "question",
    "answer",
    "tool_call",
    "tool_result",
    "state",
    "error",
    "agent_joined",
    "agent_left",
]


class Event(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    ts: int  # epoch ms, display only, never the ordering key
    channel: str
    from_: str = Field(alias="from")
    to: str | None = None
    kind: Kind
    text: str | None = None
    data: dict[str, Any] | None = None
