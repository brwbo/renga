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
- **a pm at the front door.** you talk to one project manager agent. it splits
  the goal into tasks, brings in the right agents and reports back.
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
- **marketing workers**: turn the meeting into video scripts, social posts,
  blog drafts, case studies and ad copy
- **end-of-meeting questions**: anything an agent got stuck on, asked once,
  after the call

## status

early. the design is written up and no code has shipped yet.

build order:

1. side panel showing a live transcript of a meet tab
2. notes agent in the group chat
3. one action worker end to end, with an approve button
4. the clarification loop on that worker
5. marketing workers, starting with video scripts
6. visual agent
