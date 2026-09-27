---
id: sunny-commands
type: reference
status: active
created: 2026-09-23
tags: [usage, commands, reference]
---

# Everything you can say to Sunny

Sunny reads plain language, not a command syntax. Everything below is
what to *type or say* — there is no `!` prefix and no required wording.
The phrasings listed are the ones the regex fast paths recognise
verbatim; anything close usually works too, because unmatched messages
fall through to the LLM with your memory, projects and docs as context.

**Where it works.** All of it, in every interface — the website chat,
Discord, terminal chat (`python chat.py`), and voice. They all route
through the same `assistant.handle_message()`, so behaviour is identical.
On the website, typing `/` opens a command picker over the same list.

---

## Tasks

| Say | What happens |
| --- | --- |
| `add quiz 3 in physics due friday` | One extraction → title, due date, category, class. Filed in one turn. |
| `add call the shop --due 2026-09-25` | Explicit flags win over inference entirely. |
| `add buy milk to my school tasks` | Inline category — no LLM call, instant. |
| `show my tasks` · `tasks` | Open tasks, soonest due first. |
| `mark <name or id> as done` | Complete it. |
| `my categories` | List the categories. |
| `add category <name>` · `remove category <name>` | Manage them. |

**Dates are resolved for you.** "friday", "next tuesday", "by sunday",
"tomorrow" all become real dates. A bare weekday always means the *next*
one, never a past one. A time is only set if you actually said one —
"monday morning" gets a date and no time.

**Categories are inferred.** Sunny only asks when two genuinely compete
(about one in eight, measured). When it files something automatically it
names the category in the reply, so a wrong guess is visible immediately.
See [[architecture/capture.md]].

> Late-night note: the day boundary is **5am**, so at 1am "tomorrow"
> means the day that is about to start, not the one after it.

---

## Projects

A project is a folder that Sunny reads as one body of context —
description, plan, critique, research, and any note you drop in by hand
in Obsidian. See [[architecture/project-system.md]].

| Say | What happens |
| --- | --- |
| `projects` | Everything, grouped by status. |
| `project sunny` | Scope the conversation to it. Its whole folder is loaded. |
| `plan` | Draft `plan.md` from the description. |
| `critique` | **Attack the plan.** Risks, failure modes, fixes → `critique.md`. |
| `research <question>` | Web search, compare/contrast, filed under `research/`. |
| `active` · `long-term` · `someday` | Change the focused project's status. |
| `phase building` | Move it along the lifecycle. |
| `archive` | Finished. Folder moves to `archive/`. |
| `park` | Stopped on purpose — recorded differently from finished. |
| `archived` · `show archive` | What's in the archive. |
| `unarchive <name>` | Bring one back. |
| `tasks` · `what's left` | Open tasks **for this project**. |
| `unfocus` | Leave the project, back to general chat. |

### The three statuses

- **active** — on it now
- **long-term** — ongoing, no end date
- **someday** — later, not started

A long-term project you're working on today is `active`; it goes back to
`long-term` when you step off it.

### The lifecycle

```
idea → planning → critique → refined → building → done / parked
```

Status and phase move **independently**. A `someday` project can sit at
`refined` — plan finished, waiting on time.

**Tasks added while a project is in focus belong to it**, so `what's left on Warren` answers. Outside a project, `tasks` still lists everything.

**`critique` is the one worth using.** It sits between planning and
refined on purpose: the first plan gets written while you're still
enthusiastic, so it gets attacked once while changing it is cheap. Every
risk it raises comes with a concrete failure mode and a concrete fix.

---

## Debrief

Dump what happened. Sunny asks at most two questions, then files it.

| Say | What happens |
| --- | --- |
| `debrief` | Asks for the dump. |
| `debrief: the lab ran long again, never got to the essay` | Goes straight in. |
| `cancel` | Drops it. Nothing filed. |

It asks **at most two** questions, and only where the answer changes what
gets filed — whether something becomes a dated task or a standing fact,
which of two things you meant. Often it asks none.

Two destinations, kept separate:

- **Facts** → long-term memory. Written as facts about *you*, not about
  today: "loses focus in long afternoon labs", not "the lab ran long".
- **Tasks** → the task list, with a due date where one was actually stated.

Everything filed is listed back, and the reply reports what was **written**,
not what was proposed. Filing nothing is a normal outcome and it says so.

See [[architecture/debrief.md]].


## Memory

| Say | What happens |
| --- | --- |
| `remember that I prefer blunt answers` | Stored as a fact, injected into future prompts. |
| `what do you remember` | Everything stored, plus the profile. |
| `forget <id>` | Delete one fact. |

Long-form things about you go in `sunny-vault/memory/profile.md`, which
you edit by hand. Sunny reads it and never writes it.
See [[architecture/memory.md]].

---

## Health and check-ins

| Say | What happens |
| --- | --- |
| `what's my readiness` | Garmin's Training Readiness, or the composite if that's missing. |
| `how did I sleep` | Last night's sleep and wellness. |
| `when should I work out` | Free windows ≥45min over the next 48h. |
| `check in` | Today's outstanding question. |
| `no` / `yes` | Answer it. |

The daily check-in (migraine, currently) can also be answered by
**tapping the Pi panel** — one tap, no typing.

---

## Briefings

| Say | What happens |
| --- | --- |
| `brief` | Whichever is current. |
| `morning` · `evening` | Force one. |

Morning runs 05:00–18:30, evening 18:30–05:00. The nightly brief stays up
until 5am so a late night still shows the right one.

---

## Everything else

| Say | What happens |
| --- | --- |
| `my lists` · `what's on my <name> list` | Lists. |
| `show my alarms` · `show my reminders` | Scheduled items. |
| `remind me to <thing> <when>` | Set one. Falls back to extraction when the regex can't read the time, so "monday morning" works. |
| `my classes` · `set up my classes` | Class setup from a syllabus. |
| `what's the weather` | Current conditions. |
| `what's my usage` | Claude spend against the caps. |
| `health check` | System health report. |
| `what version are you running` | Deployed commit. |
| `help` | The full list, live. |

---

## The website

`/logs` — every log Sunny writes, tailed from the end so a 4MB file costs
the same as a small one. Sources: requests, LLM usage, rules engine,
check-ins, health checks, suggestions, the app log, and **routing traces**
(which feature answered each message and how confident the match was).

Not auto-polling — a log that scrolls on its own is unreadable the moment
you try to read a specific line. Refresh is a button.

`/projects` — every project grouped by status, with its plan, critique and
open tasks. Read-mostly: creating, planning and critiquing stay in chat,
where they need a conversation rather than a form.

Other pages: `/sunny` (brief), `/chat`, `/health`, `/dashboard`, `/net`,
`/warren`, `/portal`.

## The Pi panel

The companion screen takes touch. See [[architecture/pi-companion.md]].

- **Tap anywhere** → menu opens
- **Yes / No** → answers today's check-in in one tap
- **Calendar / Weather / Tasks / Health** → jump to that pane, pinned 45s
- **Refresh** → force a data pull
- Tap empty space, or wait 20s, to dismiss
- A tap while a notification is up **dismisses the notification** instead

> Touch orientation is not calibrated yet — see the roadmap's "waiting on
> being at the device" section. The hardware works; the axes need
> measuring with `calibrate.py`.

---

## Tuning how Sunny sounds

`sunny-vault/personality.md` — five dials plus freeform guidance. Edit it
in Obsidian and it takes effect on the **next reply**, no restart.

```yaml
verbosity: 1      # 1 terse … 5 thorough
formality: 2      # 1 casual … 5 formal
humor: 3          # 1 straight … 5 playful
bluntness: 2      # 1 soften … 5 disagree early
proactivity: 5    # 1 answer only … 5 volunteer things
```

A dial at **3 is neutral and emits no instruction at all** — if you want
a style that isn't the midpoint, write it in the body text instead.

Per-project overrides go in `data/projects/<slug>/instructions.md`.

See [[architecture/personality.md]].

---

## Files you edit by hand

Sunny reads these and never writes them, which is what keeps them out of
the sync-conflict class:

| File | What it is |
| --- | --- |
| `personality.md` | How Sunny sounds |
| `memory/profile.md` | Who you are, how you work |
| `data/projects/<slug>/instructions.md` | Per-project guidance |
| `docs/instructions/*.md` | System prompts per purpose |

Anything Sunny wants to change in these goes to `log/suggestions.md` for
you to merge deliberately.
