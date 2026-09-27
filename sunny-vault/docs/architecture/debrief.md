---
id: sunny-debrief
type: component
status: active
created: 2026-09-26
tags: [debrief, memory, tasks, llm, component]
---

# Debrief

`sunny_code/components/debrief.py`

Dump what happened in whatever form it comes out. Sunny reflects it back,
asks **at most two** questions, and files the result into long-term memory
and the task list.

## Two questions is the feature

Not a default — a hard cap, enforced in code as well as in the prompt. A
cap held only by instruction is one the model talks itself out of on a
long dump.

The value of this flow is that it costs **less** effort than writing
things up properly. A flow that asks six questions is a form, and a form
is the thing you do not fill in. The prompt is told to ask nothing when
the dump is already clear, and the zero-question path goes straight to
filing.

It asks at all because a raw dump is full of things only Keaton knows:
whether "the lab ran long" is a one-off or the third time, whether "didn't
get to the essay" means the one due Friday. Those decide whether something
becomes a dated task or a standing fact — one question resolves more than
a paragraph of guessing.

## Two destinations, deliberately separate

| | Goes to | Written as |
| --- | --- | --- |
| **Facts** | `memory_store` | facts about *him*: "loses focus in long afternoon labs" |
| **Tasks** | the task list | an action, with a date only where one was stated |

They are proposed and filed separately because they **decay differently**.
A task completes and archives; a fact stays true until it does not. Mixing
them would mean either tasks polluting memory, or facts quietly vanishing
when a task is closed.

A fact true of only one day is a diary entry, not a fact, and the prompt
says so explicitly.

## Nothing is filed without being shown

Every fact and task is listed back. An assistant that silently decides
what to remember about you is one you stop trusting the first time it gets
something wrong — and the whole point of memory is that it is
load-bearing.

The reply reports what was **written**, not what was proposed. Those can
differ: `memory_store.remember()` rejects junk and a task can fail
validation. Reporting the proposal as the result would be the one lie this
flow cannot afford.

**Filing nothing is a normal outcome** and says so explicitly. Verified:
an uneventful day returns "nothing durable in that one" rather than
inventing a fact to look useful.

## Provenance

Filed items are tagged `debrief:<device>`, not just the device. For memory
in particular, *how* a fact got there is what lets you judge it later — a
debrief-filed fact and one you typed directly are different claims.

## Shape of the flow

```
debrief: <dump>        analyse()  -> summary + 0-2 questions
  answer 1             (pending: debrief_answer)
  answer 2
                       propose()  -> facts + tasks, nothing written yet
                       commit()   -> writes, returns what actually landed
```

State uses the same pending mechanism as the task wizards, with one
deliberate difference: **no `_looks_like_a_command` guard** on the answer
step. An answer to "was that the essay due Friday?" is very often "add it
for friday then", which reads exactly like a task command and would be
swallowed by that guard, losing the debrief mid-flow. `cancel` is the
escape.

## See also

- [[memory.md]] — where the facts land
- [[../TASK_SYSTEM.md]] — where the tasks land
- [[../COMMANDS.md]] — what to type
