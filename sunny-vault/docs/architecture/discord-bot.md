---
id: sunny-discord-bot
type: component
status: active
created: 2026-08-19
tags: [discord, bot, tasks, lists, alarms, reminders, server-admin, component]
---

# Discord Bot — Commands + Multi-Channel Output + Server Admin

The intended **primary** interface for Tasks (see [[../TASK_SYSTEM.md]]), [[lists.md|Lists]], and [[alarms-reminders.md|Alarms/Reminders]] — one bot, all three subsystems. Reads commands as plain messages from **one chat channel**, replies in-channel, keeps a pinned task dashboard up to date in its **own separate, read-only channel**, and posts a ping whenever an alarm/reminder comes due. The console chat (`/console`) is the fallback whenever the bot is offline. It can also administer the server itself — create/delete channels and roles, assign roles to members — since that's a Discord-only capability with nowhere else to live. Beyond the chat and dashboard channels, it can optionally *post* specific things (briefings, warnings, task changes) to further separate channels you designate — see Multi-Channel Output Routing below.

## Status

Built and connected — `sunny_code/components/discord_bot.py`, `sunny_code/components/server_admin_parser.py`. Live on a real server as of 2026-08-20.

## How It Works

- Uses the exact same routing as the console chat (`sunny_code.components.assistant.handle_message`) — natural phrasing, no `!` prefix needed, `help` works, everything behaves identically to `/console`, and covers all three subsystems (Tasks/Lists/Alarms-Reminders) through one message handler.
- **Scoped to one chat channel.** Messages anywhere else in the server are ignored entirely — including server-admin commands. The dashboard channel (see Channel Reference below) is a pure display surface — the bot never reads anything posted there.
- Every message in the chat channel gets a reply. Task-mutating commands (add/update/delete) also trigger an immediate dashboard refresh in the dashboard channel; everything else just replies.
- Long responses (>1900 characters) are split into multiple messages at line boundaries — Discord's hard limit is 2000.
- Ignores messages from any bot (including itself), so it can't loop with other bots.
- On first connect (`on_ready`), if any tracked API key is still missing, posts the same missing-key summary that's logged on startup — once per run, and skipped entirely if nothing's missing (`sunny_code/components/key_status.py` — no noise when everything's configured).

## Usage

Everything below is typed as a plain message in the **chat channel** (not the dashboard channel, which is read-only) — no `!` prefix, no slash commands. Same phrasing as `/console` and `chat.py`, since all three go through the identical `handle_message()` router. Full command reference for each subsystem lives in its own doc ([[../TASK_SYSTEM.md]], [[lists.md]], [[alarms-reminders.md]]) — this is the condensed version.

### Tasks
```text
add finish physics homework to my tasks --tag School --priority 4 --due 2026-08-20
show my tasks
mark make pizza as done
delete make pizza
```

### Lists
```text
add milk, eggs, and bread to my grocery list
what's on my grocery list
remove milk from my grocery list
my lists
```

### Alarms & Reminders
```text
set an alarm for 7am
set a recurring alarm for 7 AM every weekday
remind me to call Mom at 5 PM
what alarms are set
cancel my 7am alarm
```

### Briefing, Setup, Help

- **Briefing** — "morning" or "evening" generates a full briefing on demand (also cross-posts to `#briefings` if configured, see Multi-Channel Output Routing below).
- **Setup status** — "setup" for the full connection overview, or "setup \<name\>" (e.g. "setup weather", "setup claude") for step-by-step instructions on one integration — same live-status output as typing it into `/console`.
- **Help** — "help" (or blank/"commands"/"what can you do") prints the full command list.
- **Server admin** (channels/roles) — see the dedicated section below; these are Discord-only and use different verbs (`create a channel called ...`) from everything above.
- **Voice** — `/speak <text>` posts back a playable audio attachment (one-shot, Piper TTS, see [[tts-piper]]); `/join` has the bot join your voice channel for a real live conversation (Vosk STT + Piper TTS, see [[voice-join]]), `/leave` ends it. All three are real Discord slash commands, not plain-text.

## Server Admin (Channels & Roles)

Discord-only, and checked *before* the shared `handle_message()` router — same reason lists/alarms are checked before tasks there: a generic "delete <title>" task pattern would otherwise swallow "delete channel #general" as an attempt to delete a task titled that.

**Commands** (`sunny_code/components/server_admin_parser.py`, regex-only, no LLM — same approach as `tasks_parser.py`):
- `create/add/make a channel called <name>` — text channel
- `delete/remove channel <name>`
- `list channels` / `show channels`
- `create/add/make a role called <name>`
- `delete/remove role <name>`
- `list roles` / `show roles`
- `give <@user> the <role> role` (either order works — also `give the <role> role to <@user>`)
- `remove <@user> from the <role> role` (either order — also `remove the <role> role from <@user>`)

**Deletions run immediately — no confirmation step.** This was a deliberate choice, not an oversight: it matches the trust model every other delete command in this app already uses (task/list deletion also runs immediately). Two hard guardrails exist regardless, because these specific mistakes would break the bot itself rather than just being undesired:
- Can't delete the channel the bot is listening in (`DISCORD_CHAT_CHANNEL_ID`) — would strand it with no way to talk to you.
- Can't delete `@everyone` — Discord's API refuses this anyway, but the guard gives a clean message instead of a raw API error.

Any other Discord API failure (missing permission, role-hierarchy limit, role/channel already gone) becomes a plain-text reply — same fail-quietly contract as the rest of the app, never a crash.

**Why this can't be an interface-agnostic command like tasks/lists**: creating/deleting a channel or role requires a live `discord.Guild` object — there's no equivalent concept on `/console` or in `chat.py`. So unlike everything else the bot does, these commands are handled entirely inside `discord_bot.py` and never touch `sunny_code.components.assistant`.

**Permissions required**: the bot's role needs **Manage Channels** and **Manage Roles** in the server (see Setup below) — without them every command here returns a friendly "I don't have permission" instead of failing silently. For role commands specifically, Discord also requires the bot's own role to sit *above* any role it's creating/deleting/assigning in the server's role list — newly created roles land at the bottom by default so this is rarely an issue for new roles, but can bite if you're trying to manage a role positioned above the bot.

## Channel Reference — What to Create, What Goes Where

Binding is always by **channel ID**, never by name — Discord doesn't let the bot look a channel up by its display name, so the names below are only a naming *convention* for your own clarity, not something the code checks or enforces. Name them anything; rename them anytime; nothing breaks.

**Two roles, deliberately separate channels**, so a busy interactive chat doesn't bury the dashboard and a glanceable dashboard doesn't get cluttered with chat:

| Env var | Suggested channel name | Required? | What it's for |
|---|---|---|---|
| `DISCORD_CHAT_CHANNEL_ID` | `#chat` | **Yes** — the bot won't start without this one (see Setup below) | The one channel commands are read from: Tasks/Lists/Alarms/Reminders/setup/help/server-admin. Replies land here. Default fallback destination for every optional channel below when left unset |
| `DISCORD_TASKS_CHANNEL_ID` | `#tasks` | No — falls back to the chat channel if unset (reproduces the old single-channel behavior exactly) | **Read-only.** Hosts the pinned task dashboard only. The bot never reads anything posted here — it's a display surface, not a second command channel |

Four further optional, output-only channels:

| Env var | Suggested channel name | Required? | What it's for |
|---|---|---|---|
| `DISCORD_BRIEFINGS_CHANNEL_ID` | `#briefings` | No | A copy of the morning/evening briefing, whenever one's generated by typing "morning"/"evening" in the chat channel |
| `DISCORD_WARNINGS_CHANNEL_ID` | `#warnings` | No | The startup missing-API-key summary. Today this is its only real user — nothing else posts here yet (see [[llm-integration]]'s Error Handling section for a planned future user: Claude API failures aren't routed to Discord yet, only logged) |
| `DISCORD_TASK_UPDATES_CHANNEL_ID` | `#task-updates` | No | A log line for every successful task add/update/delete, from *any* interface — web console, terminal chat, or this bot |
| `DISCORD_HEALTH_CHANNEL_ID` | `#health` | No | The weekly Sunday-4am system health report — see [[health-check]] |

Create each channel in Discord first (by hand, or once the bot's connected: `create a channel called task-updates` in the chat channel), then copy its ID in (Developer Mode → right-click channel → Copy Channel ID) — see Setup below for the full walkthrough.

## Multi-Channel Output Routing

The bot still only ever *reads commands* from the chat channel (`DISCORD_CHAT_CHANNEL_ID`) — this is about where it *posts things*, not a second command channel. See the Channel Reference table above for what each optional channel carries. What "left unset" actually does, per channel:

- `DISCORD_TASKS_CHANNEL_ID` unset → the pinned dashboard posts in the chat channel instead (the pre-split behavior)
- `DISCORD_BRIEFINGS_CHANNEL_ID` unset → not cross-posted; the briefing still replies in the chat channel as normal (this is the one channel that doesn't fall back to re-posting elsewhere — it just doesn't duplicate)
- `DISCORD_WARNINGS_CHANNEL_ID` unset → falls back to the chat channel (its behavior before this existed)
- `DISCORD_TASK_UPDATES_CHANNEL_ID` unset → not posted anywhere extra; the pinned dashboard still updates as normal either way
- `DISCORD_HEALTH_CHANNEL_ID` unset → the weekly health report falls back to the chat channel — see [[health-check]]

**How it's wired**: `TaskEngine.on_change` (previously a bare no-arg "something changed, refresh yourself" signal used only for the pinned dashboard) now optionally receives the result message too. `discord_bot.py` combines both effects into one callback — refresh the dashboard *and*, if configured, log the message to `#task-updates`. Nothing about `TaskEngine` itself became Discord-aware; it just started passing along information it already had.

**Briefing cross-posting** works by checking `sunny_code.components.assistant.is_briefing_trigger(text)` — a tiny public helper added specifically so `discord_bot.py` doesn't have to duplicate the "morning"/"evening" trigger phrases that already live in `assistant.py`.

### What's intentionally not built here

The original plan in [[../phases.md]] ("Discord Activity Log") sketched a fuller 8-channel layout: `#calendar-actions`, `#email-actions`, `#state-changes`, and `#notion-sync` alongside the three above. Those four aren't built, and for the same reason each time — **there's no underlying feature yet that generates the event they'd log**:
- `#calendar-actions` / `#email-actions` — Calendar/Gmail (see [[google-integration]]) are read-only Q&A today; nothing in this codebase ever *takes an action* on either, so there'd be nothing to post.
- `#state-changes` — sleep/wake mode isn't tracked anywhere in the codebase yet.
- `#notion-sync` — no Notion integration exists at all.

Adding any of these three channel vars now would be dead configuration with nothing behind it — exactly the kind of thing this project's own honesty principle (see [[briefing-engine]]) argues against. Once one of those underlying features actually exists, wiring its channel is a small, isolated addition (same shape as `#task-updates` above), not a redesign.

## Pinned Dashboard

- On startup, the bot looks for a message it previously pinned (marked with a trailing zero-width space so it can recognize its own message across restarts). If found, it starts editing that one; if not, it posts a new one and pins it.
- Refreshes automatically every 5 minutes (`discord.ext.tasks.loop(minutes=5)`) and instantly on every task change, from any interface.
- Content is exactly `TaskEngine.format_dashboard()` — the same formatter the `/api/tasks/dashboard` endpoint already uses.
- Lists don't get a pinned dashboard today — only Tasks does.

## Scheduled Items (Alarms/Reminders) — Due Check

- Separate loop, `scheduled_check_loop`, runs every 30 seconds (`discord.ext.tasks.loop(seconds=30)`) — independent of the 5-minute task dashboard refresh.
- Queries `scheduled_engine.db.get_due_items(now)`. For each due item, posts `Alarm: <label>` or `Reminder: <label>` to the **chat channel** (not the dashboard channel — these are conversational pings you might reply to, e.g. "cancel my 7am alarm"), then either reschedules it (recurring items, via `next_occurrence()`) or deactivates it (one-off items).
- This is currently the **only real "sounding" mechanism** for alarms/reminders — see [[alarms-reminders.md]] for why, and for what happens when the bot isn't connected (items still get created and stored, they just never announce themselves).

## Setup

`sunny_code/main.py` checks for `DISCORD_BOT_TOKEN` and `DISCORD_CHAT_CHANNEL_ID` in `.env` at startup, and skips starting the bot entirely if either is missing (logs "Discord bot not configured — skipping", web chatbot keeps working as normal). Nothing crashes either way. `DISCORD_TASKS_CHANNEL_ID` (the dashboard channel) is optional — see Channel Reference above.

### 1. Create the Discord application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Under **Bot**, click **Reset Token** to generate a token — copy it, you'll only see it once. This goes in `.env` as `DISCORD_BOT_TOKEN`, never committed to git (`.env` is gitignored).
3. Still under **Bot**, enable the **MESSAGE CONTENT INTENT** toggle (under Privileged Gateway Intents). Without this the bot can see *that* a message arrived but not its text — commands won't parse.

### 2. Invite the bot to your server

1. Under **OAuth2 → URL Generator**, check the `bot` scope, and also check `applications.commands` (needed for `/speak` — see [[tts-piper]] — and any future slash command; skip it if you only want the plain-text commands).
2. Under Bot Permissions, check: **View Channel**, **Send Messages**, **Read Message History**, **Manage Messages** (needed to pin the dashboard), **Manage Channels** and **Manage Roles** (needed for the server-admin commands below — skip these two if you only want Tasks/Lists/Alarms and don't want the bot able to create/delete channels or roles).
3. Open the generated URL, pick your server, authorize.

If the bot's already in your server without Manage Channels/Manage Roles (or without `applications.commands`) and you want to add them later, re-run the same invite URL with those boxes checked and re-authorize — Discord updates the existing bot's permissions/scopes in place, no need to kick and re-invite.

### 3. Get the chat channel ID

1. In Discord, enable **Developer Mode**: User Settings → Advanced → Developer Mode.
2. Right-click the channel you want commands read from → **Copy Channel ID**. This goes in `.env` as `DISCORD_CHAT_CHANNEL_ID` (a plain integer, no quotes).

### 4. Configure and restart

```bash
# In .env (run.sh creates it automatically on first run if it's missing):
DISCORD_BOT_TOKEN=<your token>
DISCORD_CHAT_CHANNEL_ID=<your chat channel id>

# Optional — see Channel Reference / Multi-Channel Output Routing above.
# Leave any blank to keep that output going to the chat channel instead.
DISCORD_TASKS_CHANNEL_ID=<channel id for the read-only dashboard, or leave blank>
DISCORD_BRIEFINGS_CHANNEL_ID=<channel id, or leave blank>
DISCORD_WARNINGS_CHANNEL_ID=<channel id, or leave blank>
DISCORD_TASK_UPDATES_CHANNEL_ID=<channel id, or leave blank>
DISCORD_HEALTH_CHANNEL_ID=<channel id, or leave blank>
```

Get each optional channel's ID the same way as step 3 (right-click → Copy Channel ID) — create the channel in Discord first if it doesn't exist yet, or ask the bot to (`create a channel called task-updates`) once it's connected with Manage Channels.

Restart Sunny (`./run.sh`). Log line to confirm it connected: `Discord bot connected as <BotName> (chat channel: <id>, dashboard: <id>)`. The dashboard should post within a few seconds.

## Known Limitations

- **One chat channel.** Commands are only ever read from `DISCORD_CHAT_CHANNEL_ID` — every other channel (dashboard included) is output-only, the bot never listens on them. No per-guild/multi-server config either — fine for personal use, would need work for anything more.
- **Three real slash commands (`/speak`, `/join`, `/leave`), everything else is plain-text.** `/speak` (see [[tts-piper]]) was the bot's first `discord.app_commands` command, registered via a `CommandTree` bound directly to the bare `discord.Client` — no framework swap to `commands.Bot` needed. `/join`/`/leave` (see [[voice-join]]) followed the same pattern for live voice conversation. Tasks/lists/alarms/setup/help/server-admin are all still plain-message parsing via `handle_message()` — a future slash-command version of any of those would be a separate `@tree.command()` calling into the same `handle_message()`, not a rewrite.
- **Text channels only.** Channel creation doesn't support voice channels or categories — not asked for, easy to add later (`guild.create_voice_channel`/`create_category` alongside `create_text_channel` in `discord_bot.py`) if needed.
- **No role color/permission customization on create.** `create role <name>` makes a plain role with no color and no permissions set — matches Discord's own default for a freshly created role. Edit color/permissions in Discord's UI after creating it, or ask to add `--color` support later if this comes up in practice.

## Dependencies

- [[../TASK_SYSTEM.md]], [[lists.md]], [[alarms-reminders.md]] — the three subsystems this bot drives, all through the same `handle_message()`
- `discord.py>=2.3.0` (installed via `requirements.txt`)
- [[dashboard]] — `TaskEngine.format_dashboard()` is the shared formatter

## Implementation Checklist

- [x] Bot connects, scoped to one configured chat channel
- [x] Natural-language + legacy `!task` commands via shared `handle_message()`
- [x] Chat channel and dashboard channel split into separate, independently-configurable channels — dashboard falls back to chat if unset
- [x] Pinned dashboard, survives restarts (recognizes its own prior pin)
- [x] 5-minute auto-refresh
- [x] ~~Reaction for on-demand refresh~~ — removed when emoji were stripped project-wide (2026-08-20): Discord reactions are inherently emoji, there's no non-emoji way to keep this specific interaction. Auto-refresh (5-min + on every change) still covers it.
- [x] Long-message chunking
- [x] Graceful no-op when not configured (web chatbot unaffected)
- [x] Lists and Alarms/Reminders routed through the same bot (no separate bot/channel needed)
- [x] 30-second scheduled-item due check, posts + reschedules/deactivates
- [x] Startup missing-API-key summary posted once per run
- [x] Server admin: create/delete channels, create/delete roles, assign/remove roles on members — parser + execution unit-tested (mocked guild), including both guardrails
- [x] Multi-channel output routing: optional `#briefings`/`#warnings`/`#task-updates`/`#health` channels, each falling back to the chat channel if unset — routing + fallback unit-tested (mocked client)
- [x] **Connected to a real live server** — 2026-08-20
- [x] First slash command: `/speak` (Piper TTS) — see [[tts-piper]]
- [x] `/join`/`/leave` — live voice conversation (Vosk STT + Piper TTS) — see [[voice-join]]
- [ ] Multi-channel activity log (briefings, warnings, etc.) — separate, larger scope
- [ ] More slash command variants (optional, nice-to-have)
- [ ] Voice channels / categories / role color on create (optional, not asked for yet)
