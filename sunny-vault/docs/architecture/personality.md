---
id: sunny-personality
type: component
status: active
created: 2026-09-21
updated: 2026-09-23
tags: [personality, tuning, prompt, tts, component]
---

# Tunable personality

`sunny-vault/personality.md` — frontmatter dials plus a freeform body.
Loaded by `sunny_code/components/personality.py`.

Applies across **every** interface — chat, voice, briefs — not just the
general-chat fallback. Folding personality into each instruction file
would mean editing seven files to make Sunny less chatty.

## The dials

```yaml
verbosity: 1      # 1 terse … 5 thorough
formality: 2      # 1 casual … 5 formal
humor: 3          # 1 straight … 5 playful
bluntness: 2      # 1 soften … 5 disagree early
proactivity: 5    # 1 answer only … 5 volunteer things
```

Rendered into the prompt as **sentences, not numbers** — "3/5" means
nothing to a model without the scale, and explaining the scale every time
is wasted tokens.

**A dial at 3 emits no instruction at all.** That is the neutral
midpoint, and spending tokens to say "be moderately humorous" makes the
prompt longer without making it more specific. A style that isn't the
midpoint belongs in the body text.

Unknown dials are passed through rather than rejected: inventing one and
referring to it in the body is a legitimate way to steer the model.

## Hot reload

Not cached. A hand-edit takes effect on the **very next call**, no
restart. The file is a few hundred bytes and is read once per LLM call,
which is considerably cheaper than the call it is shaping.

## Fail quiet

A malformed personality file must never break Sunny's ability to answer.
Every failure path returns the last known-good rendering, or nothing —
never an exception into an LLM call path.

**A zero-byte file is treated as mid-edit, not as "no personality".**
Obsidian and most editors save by truncating and rewriting, so a read
landing in that window sees exactly that. Reported as not-ok so the last
good rendering is held for whatever reply is in flight.

## Human-owned

Sunny reads this and never writes it. The single exception is creating
the default file when none exists — it never overwrites, so it cannot
clobber an edit or produce a sync conflict.

Changes Sunny wants to propose go to `log/suggestions.md` for deliberate
merging. See [[vault-storage.md]].

## Where it does NOT apply

`ask_claude_json()` — the structured-extraction path — deliberately skips
personality injection. Personality shapes prose; none of it has meaning
for a JSON object whose shape is already fixed by a schema. Injecting it
would spend tokens on instructions the output format makes unfollowable,
and invite the model to editorialize inside string fields other code then
parses.

## Reaching TTS

`speech_rate_multiplier()` derives a pace hint from `verbosity`. A terse
register and a brisk delivery are the same preference in two media, so
one dial drives both rather than needing a separate speech setting that
can contradict the text one. Composes multiplicatively with
`PIPER_LENGTH_SCALE` and `tts_delivery.py`'s per-message-type multipliers.

At `verbosity: 1` the multiplier is **0.92** — slightly quicker.

`bluntness` does not reach TTS yet.

## Keaton's current settings

Terse (1), casual (2), dry humour (body text, not the dial), gentle
pushback (2), highly proactive (5).

Two of those contradict, and the body text settles it rather than leaving
the model to split the difference per reply:

- **verbosity 1 vs proactivity 5.** Terse wins the answer; proactivity
  gets exactly one extra line. "Notice, don't fill space."
- **bluntness 2 vs "keep bringing up overdue work".** Gentleness is the
  *wording* — raise it as a question, not a verdict — never the
  frequency. Softening was never meant to mean dropping it.

## versus profile.md

`personality.md` is **how Sunny behaves**. `memory/profile.md` is **who
you are**. They blur easily, and merging them makes both harder to tune.

## See also

- [[../COMMANDS.md]] — the dials, summarised
- [[memory.md]] — the other half
- [[tts-piper.md]] — how the pace hint composes
