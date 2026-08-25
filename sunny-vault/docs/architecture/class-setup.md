---
id: sunny-class-setup
type: component
status: active
created: 2026-08-25
tags: [class-setup, calendar, exam-prep, llm, component]
---

# Class Setup — Syllabus → Calendar + Memory + Reminders

Say "set up my classes" and paste a syllabus per class; Sunny extracts the schedule, puts recurring class times and all-day due-date/exam events on the real Google Calendar, drops a verbatim syllabus copy plus a generated class-info summary into the class's own vault folder, and pings `#reminders` 2 days before and the day of each deadline. Builds on [[exam-prep]] (which already reads exam dates from Calendar, and now reads class-info.md too) and [[google-integration]] (Calendar write access).

## Status

| Piece | Status |
|-------|--------|
| Recurring calendar events (real RRULE, not one-off duplicates) | Built — `google_calendar.create_recurring_event()` |
| All-day calendar events (due dates/exams) | Built — `google_calendar.create_all_day_event()` |
| Syllabus parsing (LLM, structured JSON) | Built — `syllabus_parser.py` |
| Per-class memory file | Built — `class_memory.py` |
| Syllabus + class-info copy in the class's own vault folder | Built — `class_memory.save_to_class_folder()` (2026-08-25) |
| Deadline tracking + T-2/T-0 reminder state | Built — `class_deadlines.py` |
| Proactive `#reminders` Discord ping | Built — `discord_bot.py`'s `class_reminders_loop` |
| "set up my classes" wizard | Built — `class_setup_engine.py` + `assistant.py` |

## Why Recurring Events, Not a Series of One-Offs

Google Calendar's write support (see [[google-integration]]) only ever made one-off events before this — `calendar_engine.py`'s natural-language "add X to my calendar" has no recurrence concept, deliberately narrow scope. A semester of "MWF 10:00am" class meetings needs a real recurrence rule (`RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=...`), not ~45 individual events cluttering the calendar — confirmed with the user directly rather than assumed. `create_recurring_event()` is new, separate from `create_event()`; `create_event()` itself wasn't touched.

RFC5545 requires `UNTIL` in UTC when the event carries a time component (a class meeting always does here) — a bare local date is rejected by the API. `until` is the semester's end date, pulled from that specific syllabus's own text (see Syllabus Parsing below), not asked of the user.

## Two-Phase Commit, Same Pattern as the Project Wizard

`class_setup_engine.py` splits into `preview()` (parses the syllabus, returns a recap — creates nothing) and `commit()` (called only after the user confirms — the real writes). Real calendar events are higher-stakes than a project folder, so every class gets its own recap-then-confirm step, not one blanket confirmation for the whole semester.

## Syllabus Parsing

One `ask_claude(purpose="syllabus_parse", model="sonnet")` call per class — `sunny-vault/instructions/syllabus-parse.md` asks for strict JSON: `class_name` (pulled from the syllabus itself, not supplied by the caller — see Wizard Flow below), `meeting_times` (days/start_time/end_time/location), `due_dates`, `exams` (both title+date), `semester_start`/`semester_end` (also pulled from the syllabus itself — see below), and a free-text `summary` (grading breakdown, instructor contact). Same "ask for bare JSON, defensively strip a stray markdown fence" pattern as `project_engine.py`. Sonnet, not Haiku — this is real content extraction from an arbitrary document, not a quick judgment call, matching `project_engine.py`'s and `exam_prep.py`'s reasoning for the same model choice.

Only a semester label (e.g. "Fall 2026") is given to Claude, not a date range — `semester_start`/`semester_end` are extracted from the syllabus text itself (an explicit statement, or the earliest/latest date in an included week-by-week schedule), the same "pull it from the source, don't ask the user to retype what's already there" treatment `class_name` already got. The label is used only to resolve a bare month/day elsewhere in the text to a real year. If a syllabus genuinely states no date information at all, both come back as empty strings rather than a guess — `class_setup_engine.commit()` skips creating recurring meeting events for that class in that case (due dates/exams are unaffected, since those are self-contained dates already). Never fabricates a date/time/location that isn't actually in the text — empty lists instead of guesses when the syllabus doesn't state something.

## Storage: Sunny's Own Lookup State, Plus a Copy Sitting With the User's Notes

- **`class_memory.py`** (`sunny-vault/state/classes/<slug>.md`) — one file per class: the syllabus summary plus a rendered key-dates list. Sunny-managed reference state, gitignored, used today only to count classes for `setup_guides.py`'s status line — not a user-facing surface.
- **`class_memory.save_to_class_folder()`** (`sunny-vault/KSU/<semester>/<class>/`) — two more files, written into the *same* folder [[exam-prep]] already reads the user's own hand-written topic notes from: `syllabus.md` (the pasted syllabus, verbatim, untouched by the parse) and `class-info.md` (the same summary/schedule/key-dates content `class_memory.save_class()` tracks internally, rendered as plain markdown). This is what makes the syllabus actually visible sitting next to the user's own notes in Obsidian, instead of only existing as a gitignored state file only Sunny ever reads. Both filenames are constants (`class_memory.SYLLABUS_FILENAME`/`CLASS_INFO_FILENAME`) that `exam_prep.py`'s `list_classes()` explicitly excludes from the topic-notes glob — they're reference context, not something to spaced-repetition-track "mastered" on — but `generate_study_review()` still reads `class-info.md` in as extra prompt context when it exists, ahead of the actual topic sections. Overwritten wholesale on a re-run, same "fresh paste is the new source of truth" behavior as `save_class()`; never touches any other file already in that folder.
- **`class_deadlines.py`** (`sunny-vault/state/class-deadlines/<slug>.md`) — one file per due date/exam, tracking whether its T-2 and T-0 reminder pings have already fired. Deliberately *not* reused from the existing alarms/reminders system (`scheduled_db.py`/`scheduled_engine.py`) — that system fires once per item at one trigger time; a class deadline needs two independent pings per item with its own idempotency tracking, different enough semantics that bolting it onto the personal-alarm system risked complicating both. Both stores follow the same per-item vault-markdown pattern as `tasks_db.py`.

`sunny-vault/state/classes/` and `sunny-vault/state/class-deadlines/` are gitignored, same reasoning as `state/tasks/`/`state/lists/` — personal content, never pushed. `sunny-vault/KSU/` is gitignored too (real class notes), so `syllabus.md`/`class-info.md` land there but still never get pushed to GitHub.

## Proactive Reminders: `#reminders`, T-2 and T-0

`discord_bot.py`'s `class_reminders_loop` (new, checks every 3 hours — see `CLASS_REMINDERS_CHECK_INTERVAL_SECONDS`) calls `class_deadlines.check_and_notify(post_fn)`, gated on the new `class_reminders` service (`/service class_reminders enable|disable`, same pattern as every other toggleable loop — see [[service-orchestration]]). Date-only comparison (not exact time), so the check cadence doesn't need to be precisely timed; the `t2_sent`/`t0_sent` flags on each deadline file keep a check that runs several times a day from ever double-posting. Posts to `DISCORD_REMINDERS_CHANNEL_ID`, falling back to the chat channel if unset, same fallback convention as every other optional output channel — see [[discord-bot]].

This is the first genuinely *proactive, unprompted* Discord message anywhere in this codebase — everything else (dashboard refresh, health check, alarms/reminders) is either request-triggered or a status refresh, not "Sunny decided to tell you something without being asked." Deliberately built as its own small dedicated loop rather than routed through the Layer 1-5 proactive-architecture pieces from [[proactive-architecture]] (`rules_engine.py` etc.) — those are still real but uncalled infrastructure with no proven feature yet; a purpose-built loop matching `scheduled_check_loop`'s/`health_check_loop`'s existing shape was the lower-risk choice for a well-defined, already-scoped use case like this one.

## Wizard Flow

"set up my classes" (or a close variant), or `/classsetup` in Discord, launches a multi-step conversation, same pending-follow-up mechanism as the project wizard (`assistant.py`'s `_pending` dict, 5-minute TTL, "cancel" to back out at any point). `/classsetup` doesn't do anything special — it just calls `handle_message("set up my classes", ...)` with the same `session_id` convention `on_message` already uses, so it starts the identical wizard and every reply after it is ordinary plain-text through the channel, no different from typing the trigger phrase directly. Public, not ephemeral, unlike `/speak` — the whole back-and-forth needs to stay visible in the channel.

1. Semester name (e.g. "Fall 2026") — a label only, used to resolve bare dates in a syllabus; the semester's actual start/end dates are never asked for, see Syllabus Parsing above
2. Per class, looped until "done": paste a syllabus (no separate "what's this class called" question — the class name is pulled straight from the syllabus text by the same parse) → recap showing the extracted name, derived date range, and schedule → (on yes) real creation, then back to step 2 for the next syllabus

**Class name correction, not a separate question.** `syllabus-parse.md` asks Claude to extract `class_name` directly from the text (course code + title if both appear, e.g. "BUS 2100 - Introduction to Business"); an empty syllabus with no course info anywhere comes back with an empty string rather than a guess. The confirm step accepts three kinds of reply, not just yes/no: "yes" (build it, blocked with a re-prompt if the name is still empty), "no" (skip this class entirely, move to the next syllabus), or *anything else* — treated as the correct class name, which re-shows the recap for another confirm round. This one mechanism covers both "the extraction was wrong" and "the syllabus never stated a name at all" without a separate state or question. `class_setup_engine.recap(parsed)` is the shared function both the initial parse and every correction round call, so the message is always identical in shape.

Both `class_setup_syllabus` (a syllabus paste) and `class_setup_confirm` (a correction reply) are excluded from `assistant.py`'s general `_looks_like_a_command` gate — free-form pasted text or a class name could easily contain a word that coincidentally matches some other command's trigger (a syllabus policy sentence starting with "add", for instance), and both need to be taken literally as wizard input instead.

## What Wasn't Built

- Editing/removing a previously set-up class (re-running the wizard for the same class overwrites its memory file, but doesn't touch or delete any calendar events already created for it — a stale semester's events would need manual cleanup on Google's side).
- Any conversational query surface beyond what [[exam-prep]] already provides (`my classes`, `when is my X exam`, `study review for X`) — `class_deadlines.get_upcoming()` exists as a function but has no natural-language trigger wired to it yet.
- Month-out/week-out study planning — same gap [[exam-prep]] already has; this only adds the calendar/reminder side, not new planning depth.

## Files

- `sunny_code/components/google_calendar.py` — `create_recurring_event()`, `create_all_day_event()`
- `sunny_code/components/syllabus_parser.py` — `parse_syllabus()`
- `sunny_code/components/class_memory.py` — per-class reference file + `save_to_class_folder()` (syllabus.md/class-info.md)
- `sunny_code/components/class_deadlines.py` — deadline tracking + `check_and_notify()`
- `sunny_code/components/class_setup_engine.py` — `preview()`/`commit()`, ties the above together
- `sunny_code/components/assistant.py` — the wizard's conversational state machine
- `sunny_code/components/discord_bot.py` — `class_reminders_loop`, `DISCORD_REMINDERS_CHANNEL_ID`, `/classsetup`
- `sunny_code/components/setup_guides.py` — `"setup classes"` guide + overview entry
- `sunny_code/components/exam_prep.py` — `_NON_TOPIC_FILENAMES` exclusion, `class-info.md` as review context
- `sunny-vault/instructions/syllabus-parse.md` — the syllabus-parsing system prompt

## Dependencies

- [[google-integration]] — Calendar write access, the account this all posts to
- [[exam-prep]] — the sibling feature this composes with (exam events created here are found by `exam_prep.find_exam_date()` automatically, since both use Calendar as shared state; `list_classes()`/`generate_study_review()` now also read the vault copy this feature writes)
- [[discord-bot]] — the reminder channel, check loop, and `/classsetup`
- [[llm-integration]] — `ask_claude(purpose="syllabus_parse")`

## Implementation Checklist

- [x] `create_recurring_event()` — real RRULE, weekly, bounded by `until`
- [x] `create_all_day_event()` — due dates/exams
- [x] Syllabus parsing via Claude, strict JSON schema, dates resolved against a semester label given as a year/season hint
- [x] Semester start/end dates pulled from the syllabus itself, not asked of the user (2026-08-25) — recurring meeting events are skipped, not guessed, when a syllabus states no dates at all
- [x] Per-class memory file (`class_memory.py`)
- [x] Verbatim syllabus + generated class-info copy written into the class's own `sunny-vault/KSU/` folder (2026-08-25), excluded from `exam_prep.py`'s spaced-review topic list but read as review context
- [x] Deadline tracking with T-2/T-0 idempotent reminder flags (`class_deadlines.py`)
- [x] Proactive `#reminders` Discord loop, gated on a new `class_reminders` service toggle
- [x] Multi-step wizard (semester → per-class syllabus/confirm loop), cancel-able at any point
- [x] Class name auto-extracted from the syllabus text (2026-08-25) — no separate "what's this class called" question; confirm-step reply that isn't yes/no is treated as a name correction
- [x] `sunny-vault/state/classes/` and `state/class-deadlines/` gitignored
- [x] `/classsetup` Discord slash command — starts the same wizard, public (not ephemeral) response
- [x] `"setup classes"` / bare `"setup"` overview entry, live status (class count tracked)
- [ ] Editing/removing a previously set-up class
- [ ] Natural-language query surface for `class_deadlines.get_upcoming()`
