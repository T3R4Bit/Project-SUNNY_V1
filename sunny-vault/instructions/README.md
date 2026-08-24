---
id: sunny-instructions-index
type: reference
status: active
created: 2026-08-20
tags: [llm, instructions, prompts]
---

# LLM Instructions

System prompts for Sunny's LLM-powered tasks — hand-edit these directly, no code redeploy needed. See [[../docs/architecture/llm-instructions]] for the full design.

## Structure

```
instructions/
├── README.md              (this file)
└── <purpose>.md            one file per ask_claude() "purpose"
```

## File Format

Frontmatter (`id`, `type: instruction`, `status`, `tags`) plus the system prompt itself as the body — plain markdown, no code:

```markdown
---
id: weekly-health-check-instructions
type: instruction
status: active
tags: [llm, health-check]
---

You are reviewing Project SUNNY's weekly activity summary...
```

## Naming

The filename must match the `purpose` argument passed to `ask_claude(purpose=...)`, with underscores swapped for hyphens — `purpose="weekly_health_check"` loads `weekly-health-check.md`. No match means no system prompt is auto-loaded (same as not passing one).

## Why exact-match-by-name, not search

An earlier proposal used keyword search across multiple files with a hand-maintained keyword index — real complexity (search logic, staleness risk, ambiguous multi-file matches) this project doesn't need at its actual scale. Each `ask_claude()` caller already knows exactly which task it's doing; matching by that name directly is simpler and just as effective.

## Token budget

Whatever's in one of these files is paid for on *every* call for that purpose. Keep them terse and imperative — this is the highest-leverage place to cut token spend, more than trimming the per-call user prompt.
