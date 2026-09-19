# the design teams

sixteen design roles and seven ready-made teams, ported from
[designteam](https://github.com/pablostanley/designteam-app) (mit) and redone
as pydantic models and pydantic ai agents. each team's agents are hosted in
their own [modal sandbox](https://modal.com/docs/guide/sandboxes). renga
stays on your machine, and what the agents say is posted into the team's
room.

## how a team works

every team is a room in renga, with a lead. the pm hands a brief to the
room's lead, and the team takes it from there:

1. **plan.** the lead splits the brief into a `Plan`: one assignment per
   person who's needed, and who waits on whom (words before visuals,
   research before both). if the plan names someone who isn't on the team,
   or the assignments wait on each other in a circle, the lead is sent back
   to fix it.
2. **work.** specialists produce `Work` in waves. people who don't depend on
   each other work at the same time, and each one gets the work it waited
   on.
3. **review.** the lead checks everything against the brief and writes a
   `Review`. anyone it leaves a note for does one more pass.
4. **done.** the lead posts the finished pieces for you to look at. nothing
   is sent, posted or published: it's all drafts.

when an agent is missing something, it works from a stated guess and posts
the question in the room, rather than stopping.

## the teams

| room | who | lead |
|---|---|---|
| `full-studio` | all sixteen | creative director |
| `landing-page-sprint` | researcher, copywriter, graphic designer, ux designer | researcher |
| `brand-campaign` | copywriter, graphic designer, social media designer, creative director | creative director |
| `content-machine` | copywriter, editorial designer, social media designer, ux writer | copywriter |
| `product-team` | ux designer, ux writer, graphic designer, researcher | ux designer |
| `full-stack-design` | design engineer, ux designer, graphic designer, brand strategist, content strategist | brand strategist |
| `marketing-blitz` | marketing strategist, copywriter, social media designer, seo specialist, graphic designer | marketing strategist |

the lead is the creative director when the team has one, then whoever has
the `leader` trait, then whoever is listed first.

the sixteen roles: researcher, copywriter, graphic designer, ux designer, ux
writer, editorial designer, social media designer, creative director,
design engineer, brand strategist, marketing strategist, print designer,
motion designer, accessibility specialist, content strategist, seo
specialist.

each agent has a personality: five sliders from -5 to +5 (bold to subtle,
playful to serious, experimental to conventional, verbose to concise, warm
to corporate) and traits from four groups, at most two per group. both
become lines in the agent's instructions. designteam's moods, xp, memory
and relationships are not ported: nothing is remembered between runs.

## the agent library

open **agent library** on the teams page (`#/library`). it has two halves.

**agents.** eighteen premade agents in three groups: the two meeting agents
(listener, project manager), and the sixteen design and marketing roles
above. pick a room and click **add**: the agent joins it with its role,
personality and senses. an agent made from the library remembers which role
it came from (`template`), and that's what gives it a brain.

**workflows.** rooms of library agents that work together, set up in a team
in one click: pick the team, click **set up**. each design team above is a
one-room workflow, so any team can have one. a workflow won't make a second
room with a name the team already uses.

a room has brains when its lead came from the library: a design or
marketing lead runs a crew on each brief it's handed, and a project manager
reads the meeting.

## the meeting workflow

**meeting to design and marketing** connects a meeting to the teams. it
sets up two rooms (design is part of marketing, so one room does both):

| room | who | lead |
|---|---|---|
| `#meeting` | listener, project manager | project manager |
| `#marketing` | marketing strategist, copywriter, graphic designer, motion designer, social media designer, content strategist | marketing strategist |

1. **the listener hears the call.** it has the captions sense, so the chrome
   extension posts meet's captions into `#meeting` as the listener. you can
   also type into `#meeting` yourself.
2. **the listener sends the actions.** once the meeting pauses (15 seconds
   with nothing new) or 8 lines have piled up, it reads what's new and sends
   the project manager each thing that needs doing, as an `action:` line.
   actions it already sent are marked, so it doesn't send one twice.
3. **the project manager hands it to marketing.** each action becomes a brief
   for `#marketing`, with who asked, the numbers and dates said,
   and what done looks like. it says in `#meeting` what it sent where. when
   nothing needs doing, it sends nothing.
4. **the team does it.** the brief lands with that room's lead, and the crew
   plans, works and reviews as above. the drafts come back in that room.

## set up modal

once per machine.

1. install the requirements (modal and pydantic ai are in `requirements.txt`):

   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
   ```

2. log in to modal. this opens the browser, saves a token as a profile
   called `benrwbo` and makes it the active one:

   ```bash
   .venv/bin/modal token new --profile benrwbo
   ```

   to check which profile is active, or to switch back to it later:

   ```bash
   .venv/bin/modal profile list
   .venv/bin/modal profile activate benrwbo
   ```

   `No profile named 'benrwbo' found in ~/.modal.toml` means this machine
   hasn't logged in yet: run the `modal token new` line above.

3. give the agents a model key, as a modal secret in that workspace. the
   key lives in modal, never in this repo. gemini is the default, claude works too:

   ```bash
   # gemini (the default): a key from https://aistudio.google.com/apikey
   .venv/bin/modal secret create gemini GEMINI_API_KEY=...

   # or claude
   .venv/bin/modal secret create anthropic ANTHROPIC_API_KEY=...
   export RENGA_MODEL=anthropic:claude-sonnet-5
   ```

   to keep the key out of your shell history, put it in `.env` instead
   (gitignored; `.env.example` shows the shape) and load it from there:

   ```bash
   cp .env.example .env   # then fill in GEMINI_API_KEY
   .venv/bin/modal secret create gemini --from-dotenv .env
   ```

   the provider at the front of `RENGA_MODEL` decides which secret the
   sandbox gets and which api it can reach:

   | `RENGA_MODEL` starts with | modal secret | the sandbox can reach |
   |---|---|---|
   | `anthropic:` | `anthropic` (`ANTHROPIC_API_KEY`) | `api.anthropic.com` |
   | `google:` | `gemini` (`GEMINI_API_KEY`) | `generativelanguage.googleapis.com` |

   any other provider is refused before a sandbox starts.

## run the agents

the simplest way: start renga with the agents' host inside it. every room
with brains then works on its own: crews pick up briefs, project managers
read their meetings.

```bash
RENGA_BRAINS=modal RENGA_MODEL=google:gemini-3.1-pro-preview \
  .venv/bin/python -m uvicorn renga.main:app --app-dir src --port 8020
```

`RENGA_URL` tells it where renga is when that isn't `http://localhost:8020`.

or run the host on its own, from the repo root, next to a running renga:

```bash
# one brief straight to one room's crew
PYTHONPATH=src .venv/bin/python -m renga.design.sandbox run brand-campaign "a linkedin post about onboarding in a day"

# or leave it running: crews pick up briefs, project managers read meetings
PYTHONPATH=src .venv/bin/python -m renga.design.sandbox listen

# shut every room's sandbox down
PYTHONPATH=src .venv/bin/python -m renga.design.sandbox stop
```

`--renga http://host:port` points it at a renga that isn't on
`http://localhost:8020`. with `listen` running, `scripts/demo.py` hands a
real brief to the brand campaign team.

## the sandboxes

- **one per room.** a room's first job starts a sandbox named
  `renga-<room>-<hash>` in the modal app `renga-design`. later jobs reuse
  it, so several rooms can work at once without sharing anything.
- **a job is a process inside it.** the host sends one typed `Job` on stdin:
  a crew with its members and the brief, or a project manager with the
  rooms it can hand to and the meeting so far. the agents' lines come back on
  stdout, one json object per line, which the host posts into renga. the
  sandbox never touches renga's database.
- **it shuts itself down** after 20 idle minutes, and after 24 hours at most.
  `stop` shuts them all down straight away.
- **it can only reach** its model's api (see the table above) and logfire
  (`logfire-us.pydantic.dev`, `logfire-eu.pydantic.dev`). if traces don't
  show up in logfire, check those domains first. runs work either way.
- **new code or a new model means a new sandbox.** the hash in the name is
  taken from `src/renga/design/` and `RENGA_MODEL`, so after a change the
  next brief starts a fresh sandbox with the new code, key and model. the
  old one shuts down once idle.
- **the first job for a room is slower**, because it builds the image and
  starts the sandbox.

## settings

| | |
|---|---|
| `RENGA_MODEL` | the model every agent uses. default `google:gemini-3.1-pro-preview`; `anthropic:claude-sonnet-5` for claude. passed into the sandbox when it's created |
| `LOGFIRE_TOKEN` | add it to the model's modal secret (`anthropic` or `gemini`) to trace the agents' runs in logfire |
| `RENGA_BRAINS` | `modal` starts the agents' host inside the renga server |
| `RENGA_URL` | where the host in the server finds renga. default `http://localhost:8020` |

## the code

in `src/renga/design/`:

| file | what's in it |
|---|---|
| `roles.py` | every library role as a pydantic model, with its group |
| `personality.py` | the sliders and traits, and how they become instructions |
| `presets.py` | the seven design teams, their members and traits, and who leads |
| `crew.py` | a team's pydantic ai agents and their typed hand-offs: `Plan`, `Work`, `Review`, `Line` |
| `router.py` | the project manager: reads the meeting, returns a `Routing` of `Handoff`s |
| `jobs.py` | the `Job` the host sends a sandbox, and which rooms have brains |
| `inside.py` | what runs inside a room's sandbox |
| `sandbox.py` | the host: starts or finds a room's sandbox, runs jobs, posts back. `run`, `listen`, `stop` |

and around it: `src/renga/workflows.py` (the premade workflows),
`/api/library` and `/api/workflows/<id>/start` in `src/renga/main.py`, and
the library page in `web/library.js`.

`tests/test_design.py` runs whole teams against a scripted model, and
`tests/test_library.py` runs the meeting workflow end to end the same way,
from the listener's lines to the design team's drafts. the tests need no api
key and no modal account:

```bash
.venv/bin/python -m pytest
```
