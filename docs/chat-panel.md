# the chat panel, mapped onto what's here

the briefing in `.context/attachments/6cYIq0/Chat panel — design briefing.md`
describes a 384px chat panel: header, two tabs, a live rail, a thread and a
composer that takes source material. this file says which existing code each
part lands on, what has to be built from nothing, and where the briefing and
the code disagree.

## what's built

steps 1 and 2 of the build order are in: the panel shell in the new token
system, both themes, and the live rail. the paste-to-chip flow, the context
tray and the rest of the attach menu are not.

| state from the briefing | where it is |
|---|---|
| resting — empty composer, send disabled | built |
| attach menu open — `+` rotated | built, with one item ("this tab"). the other three need steps 3 and 6 |
| ready to send — text entered, destination line, send active | built, minus the chip tray |
| no call active — live rail absent entirely | built: the rail is added to and removed from `#rail-slot`, never emptied |
| dark theme — every state above | built |
| link resolving, resolution failed, context in use | not started (steps 3 and 5) |

two things in the rail have no data behind them yet. the record dot and the
elapsed clock are real — the clock starts when the caption reader first
reports `on`. the highlight count renders only when `state.call.marks` is
non-zero, and nothing sets it, because nothing emits highlights (step 5).
the waveform is decorative and always was.

three states the briefing doesn't cover turned up in the build:

- **captions off in a meet tab.** the call exists but isn't being captured.
  the rail stays, the dot stops pulsing, and it says to turn captions on.
  that isn't the rail collapsing to an empty state — it's a different
  capture state, and dropping it would lose the only prompt telling you the
  listener is deaf.
- **a team with more than two rooms.** `renga` has eight. the segmented
  control scrolls horizontally and keeps the room you're in centred, rather
  than squeezing eight tabs into 384px. two fixed tabs is still the design.
- **no captions agent at all.** no rail, ever. the old `#deaf` line
  explaining this is gone: the briefing's anatomy is five regions, and the
  same information is on the teams page where you add agents.

what got dropped: the `#deaf` line, and the pinned "read this tab" strip —
that button is now the attach menu's first item, which is where the briefing
was sending it anyway.

what has no home yet: the header's **close** button. chrome draws its own on
the side panel, so a second one would do nothing. **expand** is there and
opens the panel in an ordinary tab. the team picker became the header title,
since renga's session title *is* which team you're looking at.

## the surface it means

`extension/` — the chrome side panel. it already is a narrow one-column chat:
header, a segmented switch, a thread, a composer. `web/` is the three-column
app and the briefing puts it out of scope ("the host application is
untouched"), except that the token test ties the two stylesheets together
(see [tokens](#tokens)).

one thing the briefing can't have: **384px**. `extension/panel.css` sets no
width, because chrome owns the side panel's frame and the user drags it. the
fixed column is real only at `http://localhost:8020/extension/panel.html`,
the tab the panel is developed in. treat 384 as the design width and a
`min-width`, not a guarantee.

## anatomy, region by region

| briefing | what's there now | verdict |
|---|---|---|
| header 48px — title, expand, close | `panel.html:12-17` `.top`: wordmark, team `<select>`, connection dot. `panel.css:37` pads it to ~56px | rework. no expand, no close — chrome draws the panel's own close. "expand" maps to opening `/extension/panel.html` in a tab, which `main.py` already serves. the team picker and the connection dot have no home in the new header |
| tabs 40px — segmented, design and research | `panel.html:28` `<nav id="rooms">`, `renderRooms()` at `panel.js:119`, `.rooms`/`.room-btn` at `panel.css:78-87` | closest match in the codebase. already a segmented control with `aria-current`. but it renders *n* rooms from the team, not two fixed groups — see [the two groups](#the-two-groups) |
| live rail 32px | `panel.html:21` `#listen`, `showListen()`/`renderSenses()`/`checkListen()` at `panel.js:57-97`, `.listen` at `panel.css:66-76` | same job, wrong shape. it's a sentence in a box saying whether captions are being heard. no elapsed time, no waveform, no highlight count. it's **hidden**, not removed (`panel.js:72`); the briefing wants it out of the dom |
| thread, the only scrolling region | `panel.html:32` `#log`, `render()`/`renderLog()`/`append()` at `panel.js:301-332` | direct match. keep as is |
| composer, grows upward | `panel.html:34-38`, submit handler at `panel.js:355`, `.composer` at `panel.css:131-137` | a single-line input and a send button. no `+`, no chip tray, no destination line. the tray and the line are new |

the briefing's "no separate roster or agent list in the panel" is already
true — the crew list lives in `web/index.html`, not the panel.

## the two groups

the briefing has two tabs, each a thread with fixed agents. the code's model
is **team → n rooms → agents in a room**, and the panel's segmented control
is built from `state.rooms` (`panel.js:195`).

the clean mapping is **a tab is a room**. per-tab context scoping then falls
out of the event log for free: `Event.channel` already scopes everything, and
`can_speak_in()` (`agents.py:136`) already stops an agent speaking outside its
room. no new concept.

what that needs: the panel currently shows every room in the team, so either
the team carries exactly two rooms, or the panel picks two and the rest go
somewhere else.

the agents the briefing names against what exists:

| briefing agent | exists as | gap |
|---|---|---|
| listener — live transcription | `transcript`, `agents.py:66`, `senses=["captions"]` | none. this one is built |
| summary — running account of what's agreed | `notes`, `agents.py:70` | close: notes does summary + decisions + action items |
| highlights — timestamped facts as they occur | — | new. nothing emits a highlight today |
| art direction | nearest is `creative-director` in `design/roles.py` | the design rooms are the seven presets in `design/presets.py`; none is three-strong in these three jobs |
| critique | — | no role judges work against constraints and what's already built |
| design system — tokens, components, conflicts | — | no role at all |

so the research tab is mostly assembled and the design tab is a new preset
(three roles in `roles.py`, one `Preset` in `presets.py`, and they get a room
and a sandbox for free from `agents.py:77-81` and `design/sandbox.py`).

`visual` (`agents.py:68`), `pm` and `actions` are unplaced by the briefing.
see [what the briefing doesn't mention](#what-the-briefing-doesnt-mention).

## tokens

**this is the part that breaks first.** `tests/test_extension.py:13` asserts
the `:root` block of `extension/panel.css` and `web/style.css` are the same
dict. adding the briefing's tokens to the panel forces them into the web app
too, which drags the host application into the new look — the one thing the
briefing puts out of scope.

**settled:** the test's regex takes the **first** `:root` block only, so that
block stays identical in both files and the panel's own tokens go on `body`
below it. the panel is a superset, the test is untouched, and nothing reaches
`web/`. the shared `:root` isn't dead weight either — the panel's dark ramp
is built out of it (`--surface: var(--night)`, `--ink: var(--bone)`, and so
on), so the two surfaces still share one palette underneath.

what collides:

| briefing | here now | note |
|---|---|---|
| `--research` `#0F6E5C`, `--design` `#8B2F6B` | `--oxblood` `#6e2222` is the only clickable accent, `--brass` `#c9a227` the only mark colour | two group colours breaks `.21st/DESIGN.md`'s "one warm accent per surface". that file has to be rewritten or it keeps steering work back to the old palette |
| `--live` `#C0392B` for the record dot | `--hot` `#e0664f` is the existing alarm colour (`.err`, `.sys.fail`, `.listen.warn`) | two reds a hair apart. either `--live` *is* `--hot`, or `--hot` moves |
| light **and** dark, `data-theme` override | dark only, `--night` ground, no light ramp anywhere | a whole light theme is new work, and every rule in `panel.css` currently hardcodes a dark assumption |
| inter tight, 13px / 11.5px, one family | ibm plex sans 14px + ibm plex mono, loaded from google fonts in `panel.html:7` | conflicts with `.21st/DESIGN.md`'s "ibm plex sans + ibm plex mono". the mono is doing real work — `.msg .time`, `.room-btn .count`, `.card-label`, `.answered` — and one family means those become `font-variant-numeric: tabular-nums`, which is what the briefing asks for on the rail anyway |
| `--s0`…`--s6`, 2/4/8/16/32/64/128 | no space tokens; 14px gutters and 6/10/12px gaps hardcoded through `panel.css` | new. the 14px gutter is off-scale and becomes 16px (`--s3`), which shifts every margin in the file |
| `--r0` 4, `--r1` 8, `--r2` 16 | one `--radius: 4px` | conflicts with `.21st/DESIGN.md`'s "4px radius". avatars stay circles |
| `--t-fast` 120 / `--t-base` 180 / `--t-slow` 260 | ad-hoc `.15s`, `.25s`, `.3s` | straight substitution |
| `--ease` `cubic-bezier(.2,.8,.24,1)` | `--ease` `cubic-bezier(.2,.7,.2,1)` | same token name, different curve. changing it in place also changes `web/style.css` under the token test |
| `--ease-pop`, attach menu and chips only | — | new, and only two users, per the briefing |

reduced motion is already handled at `panel.css:140`, but it kills animation
and transition globally — the briefing wants durations collapsed to 1ms with
the elapsed clock still ticking. the clock is javascript, so the existing rule
is compatible as written.

## the live rail's four numbers

| what it shows | where the data is |
|---|---|
| record dot | `captionState` in `background.js:14`, read through the `get-captions-status` message at `background.js:50`. gives `on` / `missing` / none — enough for "is the call being captured" |
| elapsed time | **nothing.** no call has a start time. cheapest source is the ts of the first caption event in the channel; the honest one is a `state` event (`events.py:Kind` already has `state`) when captions first report `on` |
| waveform | decorative, `aria-hidden`, needs no data |
| highlight count | **nothing.** needs highlights to exist first. once they do it's a count of events of that kind in the channel, which `/api/events` already returns |

"tapping it switches to the research tab, scrolled to the most recent
highlight" — `openRoom()` (`panel.js:204`) does the switch; scroll-to-event
doesn't exist, `renderLog()` always ends at the bottom (`panel.js:315`).

## the composer

nothing here resolves urls or attaches anything. what the existing code gives
you:

- `POST /api/chat` takes `{text, channel}` only (`main.py:ChatIn`). attachments
  need a field.
- `Event.data` is an open `dict[str, Any]` (`events.py`), so a sent message's
  context pills need **no schema change** — they ride in `data`.
- there's already a precedent for pulling outside material into a room:
  `POST /api/screen` (`main.py:screen`) saves a screenshot to `frames/` and
  emits a `tool_result` with the source in `data`. a resolved chip is the same
  move with a different source.
- resolving a github url needs a new endpoint. `httpx` is already a
  dependency, so no new package — but there's no github token and no client
  anywhere. `Team.repo` (`agents.py:28`) is the only github mention in the
  codebase and it's display-only.
- thread-scoped context ("design agents can still see 2 attachments from this
  thread") is mutable per-channel state, which the append-only log can't hold.
  `questions.py` is the pattern to copy: a second table in the same sqlite
  file, its own store, its own endpoints.
- "agents must cite which attachment a claim came from" is orchestration, which
  the briefing scopes out — but the place it lands is concrete: the typed
  hand-offs in `design/crew.py` (`Plan`, `Work`, `Review`) gain a citation
  field, and it's enforced there rather than asked for in a prompt.

## what the briefing doesn't mention

things in the panel today that the new anatomy has no slot for. each needs a
decision, not a deletion by omission:

- **the team picker** (`panel.html:15`). the panel shows one team at a time and
  the worker reads the choice from `chrome.storage` to route captions
  (`background.js:20`). the new header is title/expand/close. where does it go?
- **read this tab** (`panel.html:22-25`, `readScreen()` at `panel.js:144`) and
  the `visual` agent behind it. this fits the attach menu well — "this tab"
  beside "upload a file" — and that's probably where it belongs.
- **the no-senses line** `#deaf` (`panel.html:26`).
- **questions with option buttons** (`questionCard()` at `panel.js:215`,
  `.card.ask`). they have to survive inside the thread.
- **delegation cards** (`handoff` / `task`, `panel.js:280-294`). the briefing
  says "nothing crosses between them automatically" — but delegation is
  exactly cross-room traffic, and it's how the pm gets material made
  (`main.py:delegate`). the two rules collide; the briefing's open-decisions
  table doesn't cover it.
- **unread counts** on room buttons (`panel.js:127`). they reset on visit; the
  rail's highlight count deliberately doesn't. two counts, opposite rules,
  40px apart.
- **the connection dot** `#conn` (`panel.html:16`) and the error strip
  `#error` (`panel.html:30`) — the briefing bans toasts and alerts, so the
  error strip's in-place style already agrees with it.
- **screenshot thumbnails** in the thread (`.seen`, `panel.css:59-62`).

## build order, mapped to files

the briefing's order, with what each step touches:

1. ~~**panel shell, tokens, both themes**~~ done. `extension/panel.css`
   rewritten in two token layers, `panel.html` restructured to the five
   regions, `.21st` constraints rewritten. the token test needed no change:
   its regex reads the first `:root` block, which still matches web/.
2. ~~**live rail**~~ done. `#rail-slot` in `panel.html`, `renderRail()` and
   `setCall()` in `panel.js`, fed by the caption state in `background.js`.
   not mocked — the dot and the clock are real.
3. **paste to chip, github only** — new resolve endpoint in `main.py`, paste
   handler and tray in `panel.js`, chip styles in `panel.css`.
4. **destination line, per-tab scoping** — `panel.js` state, `ChatIn` gains a
   context field, scoping comes free from `Event.channel`.
5. **sent pills, agent citation** — a `data` convention in `events.py`, the
   attachments table on `questions.py`'s pattern, citation fields in
   `design/crew.py`.
6. **attach menu** — figma, uploads, call moments, and `readScreen()` folded in
   as "this tab".

step 1 is the only one that touches shared code. everything after it is inside
`extension/` plus new endpoints.

## decisions the code forces, on top of the briefing's own

- how the two tabs relate to teams and rooms — one team with exactly two
  rooms, or the panel picking two out of *n*?
- does delegation still cross between the tabs, given "nothing crosses
  automatically"?
- `--live` versus the existing `--hot`: one red or two?
- where the team picker goes now that the header is title/expand/close.
- whether the token test relaxes, or the panel keeps a second token block
  below the shared `:root`.
