---
id: personal-assistant-vision
type: architecture
status: proposed
created: 2026-08-23
tags: [architecture, vision, planning]
---

# Sunny — Personal AI Assistant Architecture & Feature Plan

This is not a separate track or a different version of Sunny — it's the same one system, this doc just covers the long-term end of the plan. Preserved in full here rather than flattened into [[../BACKLOG.md]] because the value is as much in the *architecture* (hybrid layers, confidence thresholds, permission levels) as in the individual features. See BACKLOG.md for the checklist-sized action items pulled out of this, organized by area, each linking back to the relevant section here.

---

## 1. Core Vision

Sunny is designed as a proactive, personal AI assistant rather than a chatbot.

The goal is the closest practical version of a **JARVIS-style assistant**:
- Understands ongoing context
- Remembers projects, preferences, routines, and decisions
- Watches for useful changes
- Proactively suggests actions
- Automates deterministic tasks without wasting LLM tokens
- Uses an LLM when reasoning or judgment is actually needed
- Learns from what is accepted, ignored, or overridden

The core principle:

> **Sunny should reduce the number of things I have to remember, check, organize, and manually initiate.**

---

## 2. College / KSU Assistant

### Proactive Campus Intelligence

Sunny should monitor information relevant to college life and surface only useful opportunities.

Potential sources: KSU events, entrepreneurship events, pitch competitions, startup competitions, networking events, internships, scholarships, business organizations, career fairs, relevant workshops, local business opportunities.

Instead of dumping notifications on me, Sunny should evaluate:
1. Does this match my interests?
2. Is the timing realistic?
3. Is it worth interrupting me?
4. Is there a deadline?
5. Have I ignored similar opportunities before?

Example: *"There's an entrepreneurship pitch competition next Thursday. It matches your business interests and you have no class during the event. Registration closes tomorrow."*

---

## 3. Proactive Test & Exam Preparation

Sunny already has access to my Obsidian notes. The assistant should use them as the primary knowledge source for studying.

**Long-term tracking**: classes, topics covered, notes created, assignments, exam dates, weak/strong topics, previous study sessions.

**~1 month before an exam**: identify what material has been covered, what hasn't been reviewed recently, which topics have weak note coverage, which topics connect together.

**~1 week before**: generate a realistic study plan based on exam date, class schedule, existing commitments, available study windows, weak topics.

**Night before**: avoid overwhelming me — surface 3-5 highest-value topics, important formulas/concepts, weak areas, a short practice quiz, links to the relevant Obsidian notes.

**Spaced review**: periodically bring back old material rather than relying on rereading. Possible pipeline: `New → Review → Weak → Retest → Mastered`.

---

## 4. Fitness / Physical Life Assistant

Help me actually maintain physical activity rather than simply reminding me to exercise.

**Schedule-aware gym planning**: examine my schedule and find realistic workout windows. Example: *"You have 85 minutes free after class. There's enough time for a workout before your next commitment."*

Considers: class schedule, travel time, existing commitments, previous workouts, recovery, available time.

Avoid excessive reminders — if I repeatedly ignore a workout reminder, Sunny should learn from that behavior (see §12).

---

## 5. Garmin Integration

Garmin data as **context, not a medical authority**: sleep, activity, training load, recovery information, heart-rate data where appropriate, daily activity, workout history.

Example: *"You've had several active days and limited sleep. Today might be better suited for a lighter workout and an earlier night."* Or: *"You have a relatively open day and haven't trained recently. There's a good workout window after class."*

---

## 6. Recipe & Food System

A personal recipe database that learns what I actually like.

**Track**: recipes I like/dislike, ingredients I commonly have/avoid, favorite cuisines, cooking time, difficulty, equipment required, approximate cost, leftover potential, nutrition information when available.

**Online recipe discovery**: search online and filter by ingredients, cooking time, difficulty, nutrition, cost, cuisine, existing ingredients, and whether I've liked similar meals before. The goal is not simply "healthy food" — it's food that is reasonably nutritious, practical, enjoyable, affordable, and realistic for a busy college schedule.

**Meal planning**: weekly suggestions using class schedule, available cooking time, grocery inventory, recipe preferences, workout/activity context.

**Campus meal plan**: a configurable meal-plan schedule (e.g. Mon/Wed = campus plan, Tue/Thu = cook, Fri = flexible) — intentionally configurable, to be tuned after the semester begins.

---

## 7. Obsidian as Sunny's Knowledge Base

Obsidian as one of Sunny's primary sources of personal knowledge.

Potential vault areas: `Classes/`, `Projects/`, `Business/`, `Recipes/`, `Fitness/`, `Personal/`, `Reference/`, `Archive/`.

Sunny should be able to: read notes, create notes, update notes, add links, add tags, rename files, move files, create indexes, detect broken links, detect duplicate information, suggest organization improvements.

### Safe file operations — permission levels

Sunny should NOT have unrestricted destructive access.

- **Level 0 — Read only**: can inspect notes but cannot modify anything.
- **Level 1 — Safe edits**: add tags, add links, update indexes, append information, create new notes.
- **Level 2 — Controlled organization**: rename files, move files, reorganize folders.
- **Level 3 — Destructive**: delete notes, bulk modify files, perform large-scale restructuring. **Requires explicit approval.**

### Confidence threshold

Sunny should estimate confidence before changing the vault:

- Confidence > 95% → perform automatically
- 80-95% → suggest the change
- < 80% → ask me

Every automatic modification should be logged.

---

## 8. Weekly Knowledge Health Check

Extend the existing weekly system health check (see [[health-check]]) into a **Knowledge Health Check**.

Inspect: broken Obsidian links, orphaned notes, duplicate notes, untagged notes, empty notes, stale information, unfinished projects, missing references, notes that should be linked, classes with missing study material.

Example: *"Your Business notes have 6 disconnected pages and 2 broken links. I can clean them up."*

---

## 9. Proactive vs. Reactive Behavior

**Reactive assistant**: "Tell me what to do." **Proactive assistant**: "I noticed something relevant. Here's what I think you should do."

Monitor: calendar changes, new assignments, exam dates, new Obsidian notes, changes to projects, GitHub activity, fitness data, meal planning, relevant business opportunities, system/server health, travel requirements. Then decide whether an action is worth surfacing.

---

## 10. Hybrid AI Architecture

The system should NOT send everything to an expensive LLM.

**Layer 1 — Sensors / event listeners.** Cheap, deterministic monitoring, no LLM calls: calendar events, file changes, GitHub webhooks, Garmin data, server health, timers, notifications, RSS/API feeds.

**Layer 2 — Rules / automation engine.** Hard-coded logic for predictable behavior:
```
IF exam < 7 days                          -> create study-prep event
IF class starts in 45 min AND travel > available time -> notify
IF new Obsidian note in Classes/           -> index note
IF workout count < target AND free window exists -> suggest workout
```

**Layer 3 — Context engine.** Maintains a compact structured state instead of sending full history to an LLM:
```
Current Context: Calendar, Active Projects, Current Classes, Upcoming
Deadlines, Recent Activity, Fitness State, Food State, Important
Preferences, Recent Decisions
```
Only relevant context gets sent to the model.

**Layer 4 — LLM reasoning.** Use the expensive model only when actual reasoning is necessary: "Is this opportunity worth interrupting Keaton?", "What should he prioritize today?", "Why is he falling behind in this class?", "How should these notes be organized?", "Which meal best fits the next three days?", "What is the best response to this situation?"

**Layer 5 — Executor.** The LLM never directly performs arbitrary actions:
```
LLM -> Structured Action -> Permission Check -> Executor -> Result -> Memory/Log
```
Example structured action: `{"action": "create_study_plan", "class": "BUS 2100", "priority": "high"}` — the executor performs the actual operation.

---

## 11. Confidence-Based Autonomy

- **Automatic** (high-confidence, low-risk): create reminders, update indexes, add tags, generate study cards, add calendar suggestions, organize non-destructively.
- **Ask first** (medium-risk): move notes, rename files, send messages, change schedules, make purchases.
- **Never automatically** (high-risk): delete large amounts of data, financial transactions, irreversible system changes, sensitive account changes.

---

## 12. Learning From Behavior

Track: `Suggested -> Accepted / Rejected / Ignored / Snoozed / Manually changed`.

If I repeatedly ignore "Study for 30 minutes at 8 PM," Sunny should stop suggesting it at 8 PM. If I consistently accept "Study between classes," Sunny should increase confidence in that pattern. Builds a personalized behavior model without huge LLM prompts.

---

## 13. Voice Pipeline (revisit vs. what's actually built)

> Written before this session's real hardware testing — see [[voice-join]] and the 2026-08-19/20 crash-fixing work for what Sunny's voice pipeline actually runs today (Vosk STT, Piper TTS, process-isolated). Kept here as the original aspiration, not a current plan.

**STT**: local speech recognition where practical — Whisper-family, streaming input, voice activity detection, partial transcription. *(Today: Vosk, chosen for being lighter-weight and genuinely real-time on this CPU-only hardware — see the STT-hardware-cost discussion this session.)*

**TTS**: Kokoro as the main voice, Piper as a lightweight fallback for simple notifications, model kept loaded in memory to reduce startup latency. *(Today: Piper is the primary voice — Kokoro was evaluated live on the actual hardware this session and measured at RTF 2.40, ~40x slower than real-time with no GPU, a severe regression versus Piper's measured RTF 0.06. Revisit if/when real GPU hardware is added — see the "better model" discussion this session.)*

---

## 14. Voice Delivery / Personality Layer

Kokoro (or whichever TTS engine) generates speech, but a separate layer should determine **how** something gets spoken:
```
LLM Response -> Delivery/Emotion Layer -> Prosody Instructions -> TTS -> Audio
```
Delivery layer determines: tone, pace, pause length, emphasis, energy, seriousness, confidence.

Examples: reminder → calm/concise; good opportunity → slightly energetic; system failure → serious/direct; casual conversation → relaxed; important warning → deliberate/slower.

Use deterministic rules for common cases, reserve an LLM call for nuanced delivery decisions. If the TTS pipeline supports markup/prosody controls, use them for pacing and emphasis.

*(Partial overlap with what's built: the response-style rewrite this session — see [[llm-integration]], `general-chat.md` — covers register/tone as TEXT content, not TTS prosody markup itself.)*

---

## 15. Low-Latency Voice Goal

Target: **< 300ms perceived response latency.** Perceived latency, not total synthesis time, is the metric that matters.

Optimize with: always-loaded STT/TTS models, streaming STT, streaming LLM output, starting TTS as soon as a complete phrase is available, parallel processing, voice activity detection, local networking, avoiding unnecessary LLM calls.
```
User speaks -> Streaming STT -> Intent detection -> Fast response planning
  -> LLM begins generating -> First sentence complete -> TTS begins speaking
  -> LLM continues generating
```
A slower full response can feel extremely fast this way.

*(Already built, 2026-08-21: sentence-boundary streaming from `ask_claude_stream()` straight into chunked TTS playback — see [[llm-integration]] and this session's "streaming LLM voice replies" work. The remaining gap versus this section's goal is STT-side streaming/partial-hypothesis latency, not the LLM/TTS half.)*

---

## 16. Local TTS Hardware

Kokoro doesn't need extreme GPU hardware — a modest NVIDIA GPU can run it comfortably, and CPU inference can be practical depending on configuration. For a low-cost dedicated GPU: a used RTX 2060 is a reasonable minimum target; an RTX 3060 12GB is the better long-term choice if the machine will also run local AI models more broadly. Choose the GPU for the whole AI stack, not Kokoro alone.

*(See this session's real "how expensive would iPhone-level STT + Claude-level TTS be" discussion — broadly consistent: ~$400-500 for a midrange 8-16GB card was the estimate there too, and revisits Kokoro as a real option once a GPU exists.)*

---

## 17. Travel / Commute Intelligence

```
Calendar Event -> Destination -> Routing API -> Current Travel Time
  -> Leave-Time Calculation -> Context Check -> Notification
```
Don't poll continuously — check when an event becomes relevant, recheck near departure, recheck if traffic changes significantly. Free/self-hosted routing options can be considered depending on whether live traffic is required.

*(Matches BACKLOG.md's existing "Commute/Traffic" gap — no live integration built yet.)*

---

## 18. Opportunity Engine

Monitor: business opportunities, internships, pitch competitions, startup events, scholarships, networking, KSU events, local events, relevant competitions.

Score each: `Relevance + Timing + Difficulty + Potential Value + Personal Interest + Deadline Urgency = Opportunity Score`. Only surface opportunities above a threshold.

---

## 19. Daily Personal Operations

A compact daily briefing — schedule, IMPORTANT (deadlines), OPPORTUNITY, FITNESS, FOOD sections — avoiding a wall of notifications. Extends the existing morning briefing (see [[briefing-engine]]) with the college/fitness/food/opportunity context from the sections above.

---

## 20. Weekly Review

Once a week, summarize: **School** (deadlines, exams, weak subjects, study progress), **Business** (opportunities found, applications, events), **Projects** (progress, blockers, next actions), **Fitness** (activity trends, consistency, recovery context), **Food** (meals used, recipes liked, grocery needs, meal-plan usage), **System** (errors, failed automations, ignored notifications, new behavior patterns — this part already exists, see [[health-check]]).

---

## 21. The Key Design Principle

Sunny should not try to be an LLM that does everything. Structurally:

```
                    SUNNY
                      |
              Context Engine
                      |
        +-------------+-------------+
        |             |             |
    Sensors         Rules        Memory
        |             |             |
        +-------------+-------------+
                      |
                LLM Planner
                      |
                Permissions
                      |
                 Executors
                      |
                   Memory
```

The LLM is the **reasoning component**, not the entire operating system. That's what allows Sunny to be proactive, fast, cheap to operate, predictable, personal, extensible, safe, and useful without constant prompting.

*(Updated 2026-08-24 — see [[proactive-architecture]] for the first real slice of this: Layer 1 sensors (`sensors.py`), Layer 2 rules engine (`rules_engine.py`), Layer 3 context engine (`context_engine.py`), and the permission-check half of Layer 5 (`vault_permissions.py`) are now built and wired into a scheduled evaluation loop — plus `suggestion_tracker.py` for §12's learning-from-behavior piece. Layer 4 (an LLM planner deciding what's worth surfacing) and the rest of Layer 5 (a structured-action executor) are still not built, and the rules engine's two seed rules only log — nothing acts on Sunny's own initiative yet. Command-path features still use hardcoded parsers and `ask_claude`/`ask_claude_stream` directly, as before.)*

---

## 22. Long-Term Goal

Interact naturally instead of issuing commands. Instead of *"Remind me to study,"* Sunny should eventually understand *"I have an exam next week, I've barely reviewed this class, and I have a free hour tomorrow"* and proactively decide *"You have an hour between classes tomorrow. I've scheduled a short review of the two topics you're weakest on."*

Gradual shift from **Command → Response** to **Observe → Understand → Decide → Suggest/Act → Learn**, while keeping the user in control of consequential actions.
