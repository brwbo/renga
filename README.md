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
- **teams, one per repo, each with its own rooms.** the home page lists the
  teams and the repo each one works on, and **new team** makes one: a name,
  a repo, its rooms, and which reader agents it starts with. inside a team, every room is a
  channel with its own agents and a lead. the pm sits in the meeting room and
  doesn't do everything itself: it delegates to another room in its team by
  handing a brief to that room's lead, who splits it across the room. the
  meeting room shows where the work went.
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
- **the design teams** (a room each): the pm delegates anything that should
  become material. the team's lead splits the brief across the room, the
  specialists work in order (words before visuals), and the lead reviews it
  all before it comes back
- **end-of-meeting questions**: anything an agent got stuck on, asked once,
  after the call

## the design teams

sixteen roles and seven ready-made teams from
[designteam](https://github.com/pablostanley/designteam-app), redone in
python. each role is a pydantic model (what it does, how it works, what it
hands over, a personality of five sliders and a few traits) and becomes a
pydantic ai agent. every hand-off is typed: the lead's `Plan`, each
specialist's `Work`, the lead's `Review`.

| room | who | lead |
|---|---|---|
| `full-studio` | all sixteen | creative director |
| `landing-page-sprint` | researcher, copywriter, graphic designer, ux designer | researcher |
| `brand-campaign` | copywriter, graphic designer, social media designer, creative director | creative director |
| `content-machine` | copywriter, editorial designer, social media designer, ux writer | copywriter |
| `product-team` | ux designer, ux writer, graphic designer, researcher | ux designer |
| `full-stack-design` | design engineer, ux designer, graphic designer, brand strategist, content strategist | brand strategist |
| `marketing-blitz` | marketing strategist, copywriter, social media designer, seo specialist, graphic designer | marketing strategist |

each team's agents are hosted in their own [modal sandbox](https://modal.com/docs/guide/sandboxes),
so teams work in parallel and apart. a sandbox stays up between briefs,
shuts down after 20 idle minutes, and can reach only the model's api and
logfire. every brief runs as a process inside it and streams its lines
back; renga stays on your machine and posts them into the room. changing
the agents' code gets you a fresh sandbox.

setting up modal (login, profile, the model key), using gemini instead of
claude, and how the sandboxes behave: [docs/design-teams.md](docs/design-teams.md).

```bash
# one brief to one team
PYTHONPATH=src .venv/bin/python -m renga.design.sandbox run brand-campaign "..."

# or leave it running: anything the pm delegates to a team's room, that team picks up
PYTHONPATH=src .venv/bin/python -m renga.design.sandbox listen

# shut every team's sandbox down
PYTHONPATH=src .venv/bin/python -m renga.design.sandbox stop
```

the model is `anthropic:claude-sonnet-5` unless `RENGA_MODEL` says otherwise
(`google:gemini-3.1-pro-preview` for gemini).

## run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn renga.main:app --app-dir src --port 8020
```

open http://localhost:8020. to play a short scripted meeting into the room:

```bash
.venv/bin/python scripts/demo.py
```

## the chrome extension

a side panel with one team's chat; pick the team at the top. what it reads
depends on the agents that team has:

- a **screen** agent (renga's `visual`) gets a **read this tab** button. it
  sends a screenshot and the page's text to the server, and the agent posts
  what it saw into its room. chrome asks once for permission to see your tabs
  the first time you click it.
- a **captions** agent (renga's `transcript`) hears meet calls: meet's own
  live captions go into that agent's room.
- a team with neither reads nothing.

screenshots are saved as files in `frames/`, never in the event log.

1. start the server (above). the extension talks to `http://localhost:8020`
2. open `chrome://extensions`, turn on developer mode, click **load unpacked**
   and pick the `extension/` folder
3. click the renga icon in the toolbar and pick a team. for captions, join a
   meet and turn them on (the cc button)

the panel says whether it's hearing the call. chrome decides which side the
panel opens on (settings, appearance, side panel position); an extension
can't choose. while working on the panel you can open it in a normal tab at
http://localhost:8020/extension/panel.html.

reading meet's captions depends on meet's page, which google changes without
notice. it's the fast first version; capturing the tab's audio replaces it.

## what's here

- `src/renga/`: the room. an append-only event log (`db.py`), one emit path
  that logs and fans out (`bus.py`), the event shape (`events.py`), the
  teams, their rooms and who is in them (`agents.py`), the teams made on the
  teams page (`teams.py`), the question queue
  (`questions.py`) and the api (`main.py`)
- `src/renga/design/`: the design teams. roles (`roles.py`), personalities
  (`personality.py`), the seven teams (`presets.py`), the pydantic ai agents
  and their hand-offs (`crew.py`), what runs in a team's sandbox
  (`inside.py`) and the host that starts sandboxes and posts back (`sandbox.py`)
- `extension/`: the chrome side panel (`panel.*`, which also reads the tab
  you're on), the caption reader that runs in the meet tab (`captions.js`)
  and the worker that carries captions to the team's captions agent
  (`background.js`)
- `web/`: the chat. a teams page with each team's repo and rooms, unread
  counts for the rooms you're not in, delegations as cards you can follow into the other room, and
  questions with their options as buttons

## status

early. the rooms, the chat and delegation work. the design teams have brains
and live in modal sandboxes; the meeting room's agents don't yet (`scripts/demo.py`
speaks for them).

build order:

1. pydantic ai brains for the agents, running on modal and posting through `/api/say`
2. ~~side panel showing a live transcript of a meet tab~~ first version in `extension/`
3. notes agent in the group chat
4. one action worker end to end, with an approve button
5. the clarification loop on that worker
6. ~~the design teams' brains~~ in `src/renga/design/`, in modal sandboxes
7. visual agent
