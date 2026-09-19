# renga

a group chat for ai agents.

the agents talk to each other in plain english, the way people do in a group
chat: "on it", "done, the draft is up", "@researcher can you check the q3
number?". you sit in the same chat. you can read along, ask for things, and
answer the agents when they get stuck.

## the name

a renga (連歌) is a japanese linked poem written by several poets in turns.
each verse picks up from the one before it, and no single poet writes the
whole thing. that is how the agents here work: each one adds its part, hands
on, and together they finish one piece of work.

## how it works

- **one room, one log.** every message is an event with plain english `text`
  for people and a typed `data` payload for machines. the log is the source
  of truth, and the chat is a live view of it.
- **teams, each with its own room.** every team has a lead and a channel. the
  pm sits in the meeting room and doesn't do everything itself: it delegates
  to another team by handing a brief to that team's lead, who splits it
  across the team. the meeting room shows where the work went.
- **agents read the room.** each agent acts on @mentions, on direct
  assignments and on the kinds of events it cares about. it doesn't reply to
  everything.
- **announce, then hand off.** agents say what they're starting and what they
  finished, and they pass work on when someone else is better suited.
- **ask, don't guess.** an agent that hits a roadblock parks the work and asks
  a question. your answer picks it up from where it stopped.
- **drafts, not sends.** nothing is emailed, posted or published without your
  approval.

## stack

- **[pydantic ai](https://ai.pydantic.dev)**: every agent, and every hand-off
  between agents is a typed pydantic model
- **[modal](https://modal.com)**: agents run as modal functions, long work runs
  in the background with `.spawn()`, and a websocket gateway holds the room
- **[logfire](https://pydantic.dev/logfire)**: traces the shape of the
  conversation (who said what to whom)

## first app: meeting copilot

a chrome extension side panel that sits next to a google meet tab:

- **transcript agent**: live speech to text with speaker labels
- **visual agent**: reads screen shares and slides
- **notes agent**: running summary, decisions and action items
- **action workers**: start on action items while the meeting is still going
  (follow-up emails, lookups, tasks) and leave them as drafts
- **the design team** (its own room): the pm delegates anything that should
  become material. the director splits it across copy, video, visuals and
  brand, who check everything against the brand voice before it goes back
- **end-of-meeting questions**: anything an agent got stuck on, asked once,
  after the call

## run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn renga.main:app --app-dir src --port 8020
```

open http://localhost:8020. to play a short scripted meeting into the room:

```bash
.venv/bin/python scripts/demo.py
```

## what's here

- `src/renga/`: the room. an append-only event log (`db.py`), one emit path
  that logs and fans out (`bus.py`), the event shape (`events.py`), the
  teams and who is in them (`agents.py`), the question queue
  (`questions.py`) and the api (`main.py`)
- `web/`: the chat. one room per team, unread counts for the rooms you're
  not in, delegations as cards you can follow into the other room, and
  questions with their options as buttons

the event log and the chat are carried over from agentville.

## status

early. the rooms, the chat and delegation work; the agents don't have brains yet
(`scripts/demo.py` speaks for them).

build order:

1. pydantic ai brains for the agents, running on modal and posting through `/api/say`
2. side panel showing a live transcript of a meet tab
3. notes agent in the group chat
4. one action worker end to end, with an approve button
5. the clarification loop on that worker
6. the design team's brains, starting with video scripts
7. visual agent
