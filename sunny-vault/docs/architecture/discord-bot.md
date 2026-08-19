---
id: sunny-discord-bot
type: component
status: active
created: 2026-08-19
tags: [discord, bot, tasks, lists, alarms, reminders, component]
---

# Discord Bot — Tasks Channel

The intended **primary** interface for Tasks (see [[../TASK_SYSTEM.md]]), [[lists.md|Lists]], and [[alarms-reminders.md|Alarms/Reminders]] — one bot, one dedicated channel, all three subsystems. Reads commands as plain messages, replies in-channel, keeps a pinned task dashboard up to date, and posts a ping whenever an alarm/reminder comes due. The console chat (`/console`) is the fallback whenever the bot is offline.

## Status

✅ Built (`sunny_code/components/discord_bot.py`) — code is complete and unit-verified, but **not yet connected to a real Discord server**, since that requires a bot token and channel ID only you can create. See Setup below.

## How It Works

- Uses the exact same routing as the console chat (`sunny_code.components.assistant.handle_message`) — natural phrasing, no `!` prefix needed, `help` works, everything behaves identically to `/console`, and covers all three subsystems (Tasks/Lists/Alarms-Reminders) through one message handler.
- **Scoped to one channel.** Messages anywhere else in the server are ignored entirely.
- Every message in that channel gets a reply. Task-mutating commands (add/update/delete) also trigger an immediate dashboard refresh; everything else just replies.
- Long responses (>1900 characters) are split into multiple messages at line boundaries — Discord's hard limit is 2000.
- Ignores messages from any bot (including itself), so it can't loop with other bots.
- On first connect (`on_ready`), if any tracked API key is still missing, posts the same missing-key summary that's logged on startup — once per run, and skipped entirely if nothing's missing (`sunny_code/components/key_status.py` — no noise when everything's configured).

## Pinned Dashboard

- On startup, the bot looks for a message it previously pinned (marked with a trailing zero-width space so it can recognize its own message across restarts). If found, it starts editing that one; if not, it posts a new one and pins it.
- Refreshes automatically every 5 minutes (`discord.ext.tasks.loop(minutes=5)`).
- React with 🔄 on the pinned dashboard message for an instant refresh — the bot clears the reaction afterward so it's ready to use again.
- Content is exactly `TaskEngine.format_dashboard()` — the same formatter the `/api/tasks/dashboard` endpoint already uses.
- Lists don't get a pinned dashboard today — only Tasks does.

## Scheduled Items (Alarms/Reminders) — Due Check

- Separate loop, `scheduled_check_loop`, runs every 30 seconds (`discord.ext.tasks.loop(seconds=30)`) — independent of the 5-minute task dashboard refresh.
- Queries `scheduled_engine.db.get_due_items(now)`. For each due item, posts `⏰ Alarm: <label>` or `🔔 Reminder: <label>` to the tasks channel, then either reschedules it (recurring items, via `next_occurrence()`) or deactivates it (one-off items).
- This is currently the **only real "sounding" mechanism** for alarms/reminders — see [[alarms-reminders.md]] for why, and for what happens when the bot isn't connected (items still get created and stored, they just never announce themselves).

## Setup

The bot ships built but disconnected — `sunny_code/main.py` checks for `DISCORD_BOT_TOKEN` and `DISCORD_TASKS_CHANNEL_ID` in `.env` at startup, and skips starting the bot entirely if either is missing (logs "Discord bot not configured — skipping", web chatbot keeps working as normal). Nothing crashes either way.

### 1. Create the Discord application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Under **Bot**, click **Reset Token** to generate a token — copy it, you'll only see it once. This goes in `.env` as `DISCORD_BOT_TOKEN`, never committed to git (`.env` is gitignored).
3. Still under **Bot**, enable the **MESSAGE CONTENT INTENT** toggle (under Privileged Gateway Intents). Without this the bot can see *that* a message arrived but not its text — commands won't parse.

### 2. Invite the bot to your server

1. Under **OAuth2 → URL Generator**, check the `bot` scope.
2. Under Bot Permissions, check: **View Channel**, **Send Messages**, **Read Message History**, **Manage Messages** (needed to pin the dashboard and clear the 🔄 reaction after use), **Add Reactions** (optional, only if you want the bot to react to things later).
3. Open the generated URL, pick your server, authorize.

### 3. Get the tasks channel ID

1. In Discord, enable **Developer Mode**: User Settings → Advanced → Developer Mode.
2. Right-click the channel you want as the dedicated tasks channel → **Copy Channel ID**. This goes in `.env` as `DISCORD_TASKS_CHANNEL_ID` (a plain integer, no quotes).

### 4. Configure and restart

```bash
# In .env (run.sh creates it automatically on first run if it's missing):
DISCORD_BOT_TOKEN=<your token>
DISCORD_TASKS_CHANNEL_ID=<your channel id>
```

Restart Sunny (`./run.sh`). Log line to confirm it connected: `Discord bot connected as <BotName> (tasks channel: <id>)`. The dashboard should post within a few seconds.

## Known Limitations

- **One channel only.** No multi-channel support (e.g. separate `#briefings`, `#warnings` channels from the original design docs) — that's the broader "Discord Activity Log" idea in [[../phases.md]], not built.
- **No slash commands.** Plain-message parsing only, matching the chatbot's UX. Could be added later without touching the parsing logic — Discord's slash-command UI would just be another caller into `handle_message()`.
- **Single tasks channel per bot process.** No per-guild/multi-server config yet — fine for personal use, would need work for anything more.

## Dependencies

- [[../TASK_SYSTEM.md]], [[lists.md]], [[alarms-reminders.md]] — the three subsystems this bot drives, all through the same `handle_message()`
- `discord.py>=2.3.0` (installed via `requirements.txt`)
- [[dashboard]] — `TaskEngine.format_dashboard()` is the shared formatter

## Implementation Checklist

- [x] Bot connects, scoped to one configured channel
- [x] Natural-language + legacy `!task` commands via shared `handle_message()`
- [x] Pinned dashboard, survives restarts (recognizes its own prior pin)
- [x] 5-minute auto-refresh
- [x] 🔄 reaction for on-demand refresh
- [x] Long-message chunking
- [x] Graceful no-op when not configured (web chatbot unaffected)
- [x] Lists and Alarms/Reminders routed through the same bot (no separate bot/channel needed)
- [x] 30-second scheduled-item due check, posts + reschedules/deactivates
- [x] Startup missing-API-key summary posted once per run
- [ ] **Connect a real bot token and verify against a live server** — this step needs you
- [ ] Multi-channel activity log (briefings, warnings, etc.) — separate, larger scope
- [ ] Slash command variants (optional, nice-to-have)
