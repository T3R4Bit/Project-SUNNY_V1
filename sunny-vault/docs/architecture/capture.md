---
id: sunny-capture
type: component
status: active
created: 2026-09-23
tags: [capture, extraction, tasks, reminders, categories, llm, component]
---

# Capture — one structured extraction, three callers

`sunny_code/components/extract.py`

"quiz 3 in physics due friday" becomes a task, a due date, a category and
a class in **one turn**, with no wizard and no follow-up questions when
the answer is obvious.

That is the whole point: capture speed. Every question Sunny asks after
the fact is a place where the thought gets dropped.

## Before

```
you:   add quiz 3 in physics due friday
sunny: Got it — which category: General, School, Motorsports?
you:   school
sunny: Task created: quiz 3 in physics due friday
       (title keeps the date words; due date column empty)
```

## Now

```
you:   add quiz 3 in physics due friday
sunny: Task created: Quiz 3
       Category: School
       Due: 2026-09-25
       Class: Physics
```

## Three problems, one call

Assignment capture, reminder parsing and category inference were three
separate parsing problems in three places. They are the same problem:
read a scrap of natural language, return typed fields, say how sure you
are. Splitting them meant three prompts to keep in sync and three
different answers to "what date is 'friday'".

## Structured outputs, not tool use

The roadmap originally specified a forced tool call. `output_config.format`
does the same job better here: the only reason to define a tool was to
get JSON back, there is nothing to execute, and forced `tool_choice` is
rejected outright on some current models. The server constrains
generation to the schema either way.

## The category enum is the point

The category list goes into the schema as an `enum`, so an off-list value
**cannot be generated** rather than being caught afterwards. A phantom
category from a typo stops being something that can be *represented*.

Validated in code anyway — a schema is a promise about the model, not
about the network.

## Confidence decides, not the model

Each extraction reports confidence per-field. Above
`AUTO_FILE_THRESHOLD` (0.85) Sunny files it and **names the category in
the reply**, so a wrong guess is visible and correctable in one message.
Below it, Sunny asks about the *one* uncertain field rather than
restarting the wizard this module exists to delete.

That readback is what makes auto-filing safe to do at all.

### Calibration was a prompt bug, not a threshold one

The first pass auto-filed only 3 of 8 realistic inputs. The model was
scoring *missing detail* as *uncertainty* — "buy milk" got 0.7.

Fixed in the prompt, by telling it to judge **what was stated, not how
much was stated**, and that the general catch-all is a correct answer
rather than a hedge. Now 7 of 8:

| Input | Result |
| --- | --- |
| quiz 3 in physics due friday | Quiz 3 · Fri Sep 25 · #School · Physics |
| english essay draft due next tuesday | English essay draft · Tue Sep 29 · #School |
| finish the suspension writeup by sunday | Finish suspension writeup · Sun Sep 27 · #Motorsports |
| buy milk | Buy milk · #General |
| remind me to email my advisor monday | **asks** — genuinely split School/General |

Deliberately *not* fixed by lowering the threshold, which would have let
real errors through too.

## Dates

Resolved against the **logging day**, not the wall clock. At 2am on the
23rd, "today" is still the 22nd and "tomorrow" is the 23rd — matching
`day_boundary`'s 5am rule and how someone up at 2am actually talks. Using
the calendar date would make "tomorrow" mean two different things
depending on the hour.

A bare weekday always means the **next** occurrence. `due_time` is only
set when a time was actually stated — "monday morning" gets a date and no
time.

Dates are validated after the fact: `2026-02-31` satisfies
`{"type": "string"}` perfectly well and would reach a calendar call as a
crash rather than a bad guess.

## Extraction fills gaps, it never overrules

`TaskCommandParser` only truly parses when `--flags` are present;
otherwise its "title" is the raw remainder.

- **A due date from the parser** means explicit syntax was used → the
  whole result is left alone, only the category is inferred.
- **No due date** means prose → title and date both come from the
  extractor, because they were read out of one sentence as a unit. Mixing
  sources leaves the date words in a title whose date column now also
  holds them.

## Not yet wired

`capture()` already returns `kind: "reminder"` with the date resolved,
but nothing connects that to the reminder scheduler. "remind me to call
mom tomorrow at 7pm" currently becomes a task with a due date, not an
alarm that fires. That is a call site, not new logic.

## Tests

`test_extract.py` — 42 assertions, none of which call the API. The
stubbed cases are the ones where extraction would be quietly wrong: an
off-enum category reaching the task store, an impossible date, `kind:
none` becoming a task called "thanks".

## See also

- [[../COMMANDS.md]] — what to type
- [[../TASK_SYSTEM.md]] — where captured tasks land
