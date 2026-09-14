---
id: sunny-exam-prep
type: component
status: active
created: 2026-08-24
tags: [exam-prep, study, llm, claude, component]
---

# Exam Prep / Spaced Review

[[personal-assistant-vision#3-proactive-test-exam-preparation]]'s exam-prep feature, built against a real, user-confirmed vault convention rather than a guessed one.

## Status

| Piece | Status |
|-------|--------|
| Class discovery (`sunny-vault/KSU/<semester>/<class>/*.md`) | Built — `sunny_code/components/exam_prep.py` |
| Exam-date lookup via Google Calendar | Built |
| Spaced-review state tracking (new/weak/mastered) | Built |
| LLM-written study review from real notes | Built |
| Natural-language triggers ("my classes", "when is my X exam", "study review for X") | Built — `assistant.py` |
| Marking a topic's review outcome (good/weak) from conversation | Not built — `record_review()` exists as infrastructure, no conversational trigger calls it yet |
| Vision doc's month-out/week-out planning stages | Not built — this covers the "night before" output only |

## The Vault Convention

`sunny-vault/KSU/<semester>/<class name>/<topic>.md` — one file per topic, confirmed directly with the user (2026-08-24), not guessed. `list_classes()` walks every semester folder present under `KSU/` with no assumption about which one is "current" — semester folder naming (`Fall_26`, etc.) isn't parsed, just walked. `sunny-vault/KSU/` itself is gitignored, same reasoning as task/list state files: real personal content, not project source, never pushed even though the repo is private.

## Exam Dates: Google Calendar, Not a Vault Convention

There's no vault-side way to mark an exam date — dates come from [[google-integration|Google Calendar]]. `google_calendar.find_event_by_title()`'s plain substring match (query must already be a substring of the real title) is too strict for this: a query like `"BUS 2100 exam"` won't match a real calendar entry titled `"BUS 2100 Midterm Exam"`, since `"midterm"` sits in between. `find_exam_date()` checks the class name and an exam keyword (`exam`/`midterm`/`final`/`test`/`quiz`) independently against each candidate event title instead, over the next 60 days, soonest match wins.

## Spaced Review: Simplified From the Vision Doc's 5 Stages to 3

The vision doc describes `New → Review → Weak → Retest → Mastered`. This implementation persists three real states — `new`, `weak`, `mastered` — since Review and Retest are the *act* of calling `record_review()`, not states worth storing separately; modeling five persisted stages added complexity with no behavioral difference for a single-user tool. `record_review(class_name, note_stem, result)`: any stage + `"good"` → `mastered`; any stage + `"weak"` → `weak` (even a previously-mastered topic that's now shaky goes back to weak — normal spaced-repetition behavior, not a bug). State lives at `sunny-vault/data/state/exam-review/<slug>.md`, one file per (class, topic) pair, same frontmatter+slug pattern as `tasks_db.py`/`lists_db.py` — also gitignored, personal review history.

## The Study Review (the vision doc's "night before" output)

`generate_study_review(class_name)`: gathers up to 5 topics needing review (new topics first, then weak — new topics have never been looked at, so they're the highest-value use of a session), reads each topic's actual note content (capped at 2000 characters per note, keeps the prompt bounded), and hands it to `ask_claude(purpose="exam_prep_review", model="sonnet")`. System prompt at `sunny-vault/docs/instructions/exam-prep-review.md`: per-topic core concept, exact formulas/definitions, an optional short practice question only when the notes actually support one — never fabricated. Deliberately Sonnet, not Haiku, matching `project_engine.py`'s reasoning: this is real content authoring, not a quick judgment call.

## Natural-Language Commands

```
my classes / what classes am i tracking / list my classes
when is my <class> exam / when's the <class> exam
study review for <class> / exam review for <class> / review my <class> notes
```

All routed directly through `assistant.py` as plain function calls (`exam_prep.py` has no engine class or `try_execute()` contract — it's stateless module functions, same shape as `health_check.py`/`setup_guides.py`, not `TaskEngine`-style), so no signature changes were needed anywhere else `handle_message()` is called from.

## What's Deliberately Not Built This Pass

- **Marking a review's outcome from conversation** — `record_review()` is real, tested infrastructure, but nothing in `assistant.py` calls it yet. The natural next step (a "how did that go?" follow-up after a study review, or a real practice-quiz-with-grading flow) needs real usage first to know what shape actually fits.
- **Month-out and week-out planning** — the vision doc's earlier stages (identify what's covered, generate a study plan a week out) aren't built; only the night-before review exists.
- **GitHub/file-change-triggered proactive prompting** — this is reachable today only by asking; nothing surfaces a study review on its own initiative yet (that's Layer 4, not built — see [[proactive-architecture]]).

## Files

- `sunny_code/components/exam_prep.py` — everything above
- `sunny-vault/docs/instructions/exam-prep-review.md` — the study-review system prompt
- `sunny_code/components/assistant.py` — natural-language triggers, response formatting

## Dependencies

- [[google-integration]] — the only source of exam dates
- [[llm-integration]] — `ask_claude(purpose="exam_prep_review")`
- [[vault-storage]] — the slug/frontmatter pattern review state follows
- [[proactive-architecture]] — a natural future home for a "surface a review unprompted" rule, once Layer 4 exists

## Implementation Checklist

- [x] Class discovery under the real `KSU/<semester>/<class>/` convention
- [x] `find_class()` — case-insensitive exact then substring match
- [x] `find_exam_date()` — independent class-name + exam-keyword matching, not strict substring
- [x] 3-state spaced-review tracking (new/weak/mastered), per-topic vault-markdown state
- [x] `topics_needing_review()` — new-then-weak ordering
- [x] `generate_study_review()` — real LLM-authored review from actual note content, bounded prompt size
- [x] Natural-language triggers, all three commands, cross-interface (terminal chat/Discord/voice/Pi companion)
- [x] `sunny-vault/KSU/` and `state/exam-review/` gitignored — personal content, never pushed
- [ ] A conversational way to record a review outcome (good/weak)
- [ ] Month-out/week-out planning stages
- [ ] Proactive surfacing (needs Layer 4 — see [[proactive-architecture]])
