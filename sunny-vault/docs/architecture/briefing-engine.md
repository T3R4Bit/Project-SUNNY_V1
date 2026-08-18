---
id: sunny-briefing
type: feature
status: active
created: 2026-08-18
tags: [feature, briefing, morning, scheduler]
---

# Briefing Engine

Daily morning and evening briefings delivered via voice. A fixed-format script with slots filled from APIs — no LLM calls, deterministic output, fast and cheap.

## Concept

Like a news anchor reading a teleprompter with live data inserted. Structure is fixed, content comes from direct API calls. Keeps token spend near zero while delivering personalized information.

## Core Principle

**Templates first, tokens last.**

- Fixed briefing order (not generated)
- API calls for all facts (calendar, weather, traffic)
- LLM only if interpretation is needed (e.g., "should I worry about this email?")

## Briefing Structure

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

| Data | Source | Fallback |
|------|--------|----------|
| Calendar events | Notion/Google Calendar API | Hardcoded example |
| Weather | Weather API (OpenWeatherMap, etc.) | Last known forecast |
| Tasks (open/due) | Notion or SQLite | Empty list |
| Email (urgent/action) | Email API (header parsing) | Skip section |
| Commute/traffic | Google Maps/traffic API | Hardcoded average time |
| Location | Tailscale or location API | Home (default) |
| Yesterday's incomplete | Obsidian vault or database | Query yesterday's log |

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

- [ ] Calendar API integration
- [ ] Weather API integration
- [ ] Traffic API integration
- [ ] Task summary query
- [ ] Email header parsing
- [ ] Template structure (hardcoded text)
- [ ] Text-to-speech integration
- [ ] Scheduler (7am, 9pm jobs)
- [ ] Error handling for each API
- [ ] Dashboard integration
- [ ] Test with [[clock]] speaker
- [ ] Tune TTS speed/pauses
