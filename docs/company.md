# aurelia

fictional universal bank. frankfurt, 1871. this file is the source of truth
for how aurelia looks and writes.

use it when a call ends: take the transcript and the github trail, and write
marketing a person can review without having been in the room. drafts only.
nothing ships until a marketer says so.

## identity

| | |
|---|---|
| name | aurelia |
| category | universal bank |
| founded | 1871 · frankfurt |
| network | 18 markets, 2,400 branches |
| promise | if it happened, we can print it |
| line | the minutes are the brief |

retail, corporate, correspondent. a large european bank that writes like a
ledger: dry, exact, slightly amused. not a fintech. not a slogan factory.

## how to write from a source

the transcript is canon. github is a source, not a vibe. the marketer was
not on the call.

1. **what happened.** the decision, the ship, the number. first line.
2. **the quote.** their words, or the pr title, or the version. second line.
3. **why it matters.** one clause. then stop.

one fact per piece: one number, one name, or one quote. a second fact is a
second piece. if they said forty minutes, write forty minutes. do not upgrade
a complaint into a category.

no exclamation marks. no "we're excited". no "unlock", "journey", "seamless",
"empower", "innovation", "tailored to you". if it's good, the fact is enough.

## voice

write like a frankfurt lawyer who reads novels. short sentences. concrete
nouns. european understatement. you may be dry; you may not be cute. no puns
on "interest". compliance is a constraint, not a personality.

| we say | not |
|---|---|
| forty minutes off the swift confirm. | unlock seamless cross-border flows. |
| v2.4 is on main. nostro matches. | we're excited to announce a new era. |
| lyon wants the frankfurt view. | empowering clients across europe. |
| they refused the bundled fee. | flexible pricing, tailored to you. |
| belgian ibans still fail the check. | service quality is our priority. |

name people as they appeared ("the treasurer in lyon"), not as a class
("our valued corporate clients"). name the thing as it exists in the repo
("payments reconciliation v2.4"), not as a benefit ("a smarter way to
reconcile").

## colour

night is the institution. paper is the statement. lamp is the next action
(one per surface). dawn is a close. signal is a status, never a celebration.
if two accents compete, delete one.

roughly 80% night, 15% paper, 5% meaning.

### ramps

| token | hex | role |
|---|---|---|
| night 950 | `#05070F` | ground, `--color-bg` |
| night 900 | `#0A0E23` | surface |
| night 800 | `#131A3C` | surface raised |
| night 700 | `#1F2954` | raised hover |
| night 600 | `#303C6E` | faint fill |
| paper 050 | `#FBF8F2` | type, `--color-text` |
| paper 100 | `#F4EFE4` | cards on night |
| paper 200 | `#E7DFCE` | rules, muted edges |
| paper 300 | `#D3C8B2` | captions on night |
| lamp 300 | `#FBD9A8` | lamp light |
| lamp 400 | `#F5BC78` | lamp hover |
| lamp 500 | `#EC9E4B` | accent. the one. |
| lamp 600 | `#C87B2D` | accent on paper |
| dawn 400 | `#F09AA4` | close, pull-quote |
| dawn 500 | `#DE6F81` | close emphasis |
| dawn 600 | `#B44F63` | close on paper |
| signal 400 | `#7FD8CB` | link, wayfinding |
| signal 500 | `#4FBCAE` | status ok |
| signal 600 | `#2F8C81` | signal on paper |

### aliases

| token | hex |
|---|---|
| text muted | `#B8B4AB` |
| text faint | `#7D7A74` |
| border | `#262A3A` |
| on accent | `#05070F` |
| settled | `#4FBCAE` |
| pending | `#EC9E4B` |
| fail | `#E2574C` |
| info | `#8AA6F0` |

lamp 500 on night; lamp 600 for text on paper. signal 400 on night, signal
600 on paper. text below 16px stays high contrast — muted is a hierarchy
tool, not a default.

## type

fraunces carries the feeling. inter carries the minutes. jetbrains mono
carries anything a bank would print on a statement. all three are on google
fonts.

fraunces 300 for display (`opsz` 144, `SOFT` 40, `WONK` 1). italic 300
(`SOFT` 90, `WONK` 1) for pull-quotes only. inter 600 for titles, 400 for
body. mono 500 for statements, refs and data.

sizes in px. tracking in em. line-height in px, or a percentage that does
not land on a subpixel.

| token | size | typical use |
|---|---|---|
| micro | 11px | board labels, mono caps |
| caption | 13px | meta, hex labels |
| body-sm | 15px | dense ui |
| body | 17px / 27px | reading, max 66ch |
| body-lg | 19px | lead-in |
| title-3 | 21px / 26px | section titles, −0.01em |
| title-2 | 28px | data, prices, refs |
| title-1 | 48px | page titles |
| display-2 | 68px | italic pull-quote |
| display-1 | 112px / 108px | hero, −0.028em |

post lockups (1080 square) sit on a separate scale: eyebrow 16, body 23,
lockup 33, data-sm 60, display-sm 65, display-md 86, display 108, data 119.
gutter 76px.

| tracking | value |
|---|---|
| display | −0.028em |
| tight | −0.01em |
| normal | 0 |
| wide | 0.08em |
| board | 0.18em, uppercase, mono |

| leading | value |
|---|---|
| tight | 96% |
| snug | 120% |
| normal | 160% |
| loose | 175% |

weights: 300 light, 400 regular, 500 medium, 600 semibold. no 700.

## space and shape

| step | px |
|---|---|
| 1 | 4 |
| 2 | 8 |
| 3 | 12 |
| 4 | 16 |
| 5 | 24 |
| 6 | 32 |
| 7 | 48 |
| 8 | 64 |
| 9 | 96 |
| 10 | 128 |

desktop 1440. guide container 1180.

| radius | px |
|---|---|
| sm | 4 |
| md | 10 |
| ticket | 14 |
| lg | 18 |
| xl | 28 |
| pill | 999 |

## mark

a closed loop with one point of contact — the moment a large bank actually
touches someone. body, orbit, contact. the −22° tilt is fixed. do not redraw
it for campaigns.

wordmark: **Aurelia**, fraunces, next to the mark. lockup on night, mark
alone, lockup on paper. nothing else is part of the mark.

## motion

the background is the only thing that moves. one mesh-gradient shader behind
hero and confirmation surfaces, slow enough to notice on the second look.
three presets, no ad-hoc parameters. easing is always
`cubic-bezier(.2, .7, .2, 1)` — a bank does not bounce.

| preset | speed | use |
|---|---|---|
| nightfall | 0.16 | after hours, markets closed, homepage, the recap |
| daybreak | 0.12 | settlement morning, confirmations, follow-up |
| vault | 0.07 | ambient, small cards, loading, empty states |

if two things move, one of them is wrong.
