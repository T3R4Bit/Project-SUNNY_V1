---
id: sunny-briefing
type: feature
status: active
created: 2026-08-18
tags: [feature, briefing, morning, scheduler]
---

# Briefing Engine

Daily morning and evening briefings delivered via voice. A fixed-format script with slots filled from APIs — no LLM calls, deterministic output, fast and cheap.

## Status

| Section | Status |
|---------|--------|
| Tasks | ✅ Real — queried live from `tasks.db` |
| Weather | ⚠️ Not connected — needs `OPENWEATHERMAP_API_KEY` |
| Calendar | ⚠️ Not connected — needs `GOOGLE_CALENDAR_API_KEY` |
| Email, Commute, Health, News, Motorsports | ⚠️ Not connected — no integration built yet |

**The engine never fakes an answer for an unconnected source.** Instead of showing mock data as if it were real, each section/question says explicitly what's missing (e.g. "Not connected — needs OPENWEATHERMAP_API_KEY in .env"), and every time that happens it's logged to [[../../log/requests.md|sunny-vault/log/requests.md]] — see "Data Source Honesty & Request Logging" below.

## Concept

Like a news anchor reading a teleprompter with live data inserted. Structure is fixed, content comes from direct API calls. Keeps token spend near zero while delivering personalized information.

## Core Principle

**Templates first, tokens last.**

- Fixed briefing order (not generated)
- API calls for all facts (calendar, weather, traffic)
- LLM only if interpretation is needed (e.g., "should I worry about this email?")

## Briefing Structure

The examples below show the **target format** once every source is connected. Today, only the tasks section shows real data — every other section renders a "Not connected" line instead of these example values (see Status above).

### Morning Briefing (7:00 AM)

```
🌅 Good morning.

📅 You have 3 events today:
   - 9:00am: Biology lecture (in 2 hours)
   - 2:00pm: Lab practical (6 hours)
   - 7:00pm: Dinner with friends (expected duration 2 hours)

🌡️ Weather: 72°F, partly cloudy, 20% chance of rain.

✅ Tasks open: 5 high-priority, 2 due today.
   Top priority: "Finish physics homework" (due 3:00pm)

📧 Email summary: 12 new emails.
   Urgent: 2 (flagged)
   Action items: 3
   
🚗 Commute: 28 minutes to campus via I-95. 
   Light traffic expected.

Yesterday's incomplete:
   - "Read chapter 5" (not started)
   - "Review notes" (partially done)

Have a great day!
```

### Evening Briefing (9:00 PM)

```
🌙 Good evening.

📊 Today recap:
   - Completed 4 tasks
   - Attended 3 events
   - Processed 24 emails

✅ Tasks status: 3 remaining (2 overdue)
   Top: "Engine rebuild plan" (high priority, no due date)

📅 Tomorrow preview:
   - 8:30am: Gym
   - 10:00am: Physics lecture
   - 3:00pm: TA office hours

🎯 Recommended: 
   - Finish "physics homework" before 3pm event
   - Schedule time for "engine rebuild" planning

Sleep well!
```

## Data Sources (No LLM Required)

| Data | Source | Status |
|------|--------|--------|
| Tasks (open/due) | SQLite (`tasks.db`) | ✅ Live today |
| Calendar events | Notion/Google Calendar API | ⚠️ Not connected |
| Weather | Weather API (OpenWeatherMap, etc.) | ⚠️ Not connected |
| Email (urgent/action) | Email API (header parsing) | ⚠️ Not connected |
| Commute/traffic | Google Maps/traffic API | ⚠️ Not connected |
| Location | Tailscale or location API | ⚠️ Not connected |
| Yesterday's incomplete | Obsidian vault or database | ⚠️ Not connected |

## Data Source Honesty & Request Logging

The engine checks whether each source is actually wired up (`sunny/components/data_sources.py`) before answering with it:

```python
if is_configured("weather"):
    ...  # would call the real API (not built yet)
else:
    return "⚠️  Not connected — needs OPENWEATHERMAP_API_KEY in .env"
```

Every time a briefing section or a Q&A question hits an unconnected source — or a task command fails to parse or validate — it's appended to `sunny-vault/log/requests.md` (`sunny/components/request_log.py`):

```
**2026-08-19T07:00:00Z** [MORNING_BRIEFING] sections without a real data source: weather, calendar, email, commute, health, news, motorsports
**2026-08-19T09:14:02Z** [QA_QUESTION] "What's the weather?" — needs OPENWEATHERMAP_API_KEY in .env
**2026-08-19T09:15:40Z** [TASK_COMMAND] "mark xyz as done" — Invalid update command format
```

**Why this matters**: instead of a vague TODO list, `requests.md` becomes a real usage log of exactly which integrations are actually being asked for — a natural way to prioritize which mock data source (weather, calendar, etc.) to wire up to a real API next.

## Text Generation (Hardcoded Templates)

No LLM involved. Pure templating:

```python
def generate_morning_briefing(calendar, weather, tasks, email, traffic):
    greeting = "Good morning."
    
    # Calendar section
    events = calendar.get_today()
    event_text = "\n".join([
        f"   - {e['time']}: {e['title']}" 
        for e in events
    ])
    
    # Weather section
    weather_text = f"{weather['temp']}°F, {weather['condition']}"
    
    # Tasks section
    open_tasks = tasks.filter(status='open')
    task_count = len([t for t in open_tasks if t['priority'] >= 4])
    
    # ... more sections ...
    
    return f"""🌅 {greeting}

📅 You have {len(events)} events today:
{event_text}

🌡️ Weather: {weather_text}

✅ Tasks open: {len(open_tasks)} total, {task_count} high-priority...
"""
```

## Scheduling

- **Morning briefing**: 7:00 AM daily (configurable)
- **Evening briefing**: 9:00 PM daily (configurable)
- **Delivery**: Voice over [[clock]] speaker
- **Fallback**: Discord message if voice fails

## Task Integration

See [[task-system]] for task counts and status.

The briefing mentions:
- **Open tasks**: "You have 5 open tasks, 3 due this week"
- **High priority**: Mentions top 2-3 priority items
- **Overdue**: "2 tasks overdue since yesterday"
- **Yesterday incomplete**: "Yesterday's uncompleted: Read chapter 5, review notes"

## Email Integration

See [[email-processing]] for email triage.

The briefing includes:
- **Urgent emails**: Count and brief subject lines
- **Action items**: Emails flagged as needing reply
- **Sender patterns**: "2 emails from your professor" (if meaningful)

## Failure Handling (Fail Quietly)

If any data source fails:

```
Weather API down:
  → Skip weather section, continue with calendar

Email API timeout:
  → Skip email section, continue with tasks

Calendar API down:
  → "Your calendar is unavailable" + proceed

All APIs down:
  → Minimal briefing: time, date, battery
```

**Never crash, never skip the entire briefing.**

## Voice Delivery

- **Text-to-speech**: Sonic API (natural voice)
- **Fallback**: Piper TTS (free, robot-like but acceptable)
- **Speed**: ~100-120 words per minute
- **Pauses**: Between sections, after times/numbers
- **Tone**: Calm, informative, not robotic

See [[voice-io]] for TTS details.

## Optional: Email Triage (LLM)

If email subject summary is ambiguous:
- "Is this from my professor? Yes/No/Unknown"
- "Is this urgent? Yes/No/Unknown"

The LLM answers **only** classification questions, not retrieval. Email subjects and sender are already known.

See [[llm-integration]] for LLM calls.

## Cost

- **API calls**: 2-5 per briefing (weather, calendar, traffic)
- **LLM calls**: 0 typical, 1-2 optional (email triage)
- **TTS**: 1 call, ~500 words, Sonic API ~$0.01
- **Daily cost**: ~$0.03-0.05

**Monthly**: ~$1 for 2 briefings/day × 30 days

## Dashboard Integration

The [[dashboard]] shows:
- Last briefing time
- Next scheduled briefing
- Briefing success/failure status
- Average briefing duration

## Future Enhancements

- **Habit tracking**: "Did your 3-mile run today? You've done it 18/30 days"
- **Smart scheduling**: Shift briefing time based on calendar (earlier if early meeting)
- **Custom sections**: "Your package will arrive by 3pm" (if tracked)
- **News briefing**: Optional news headlines (if subscribed)

## Dependencies

- [[brain]] — Execution environment
- [[clock]] — Voice output device
- [[voice-io]] — TTS pipeline
- [[task-system]] — Task counts, status
- [[email-processing]] — Email summary
- [[llm-integration]] — Optional email triage
- [[networking]] — API access
- Calendar API — Event data
- Weather API — Forecast data
- Traffic API — Commute data

## Implementation Checklist (Phase 2)

- [x] Template structure (hardcoded text)
- [x] Task summary query — live against `tasks.db`
- [x] Honest "not connected" messaging for unconfigured sources + logging to `sunny-vault/log/requests.md`
- [ ] Calendar API integration
- [ ] Weather API integration
- [ ] Traffic API integration
- [ ] Email header parsing
- [ ] Text-to-speech integration
- [ ] Scheduler (7am, 9pm jobs)
- [ ] Error handling for each API (once APIs exist — today's "not connected" state isn't a failure case, it's the default)
- [ ] Dashboard integration
- [ ] Test with [[clock]] speaker
- [ ] Tune TTS speed/pauses
