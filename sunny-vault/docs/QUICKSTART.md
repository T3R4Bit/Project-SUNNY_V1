---
id: sunny-quickstart
type: guide
status: active
created: 2026-08-18
tags: [getting-started, setup, running]
---

# Quick Start — Get Running in 30 Seconds

## Step 1: Make Launcher Executable

```bash
chmod +x run.sh
```

## Step 2: Run

```bash
./run.sh
```

Server starts automatically at: **`http://127.0.0.1:5000`**, which redirects to the console at **`http://127.0.0.1:5000/console`**

No manual Python environment setup required — `run.sh` creates and manages its own virtual environment automatically on first run, and reuses it on every run after.

---

## What You Get

### Console — Chat + System Status
- One page at `/console` (`/` and the old `/chatbot` both redirect there)
- Chat panel: talk to the briefing engine and task system; type `setup` for
  step-by-step instructions on connecting any API
- Sidebar: live CPU, RAM, disk, network, and temperature stats (refreshes
  every 2s), plus Google sign-in status
- Works over Tailscale (access from phone)

### Briefing System
- Morning briefing (9 sections)
- Evening briefing (7 sections)
- Q&A engine (ask anything)
- Tasks are queried live from `tasks.db`; calendar/weather/email/commute/health/news say "not connected" honestly instead of faking data — no live APIs wired up for those yet

### Task Management
- Create, update, delete tasks
- Filter by tag, status, priority
- Hardcoded commands (no LLM parsing)
- Driven through the console chat/API today; a Discord bot is built and is the planned primary interface (needs a bot token connected) — see [[./TASK_SYSTEM.md]]

### Lists & Alarms/Reminders
- Named checkable lists (groceries, packing, anything) — see [[./architecture/lists.md]]
- Time-based alarms and reminders that ping the Discord tasks channel when due — see [[./architecture/alarms-reminders.md]]
- Same natural-language, no-LLM philosophy as tasks; both route through the same console chat/Discord bot

---

## Try These Commands

In the console, type:

```
help                             → What Sunny can do
setup                            → What's connected, what needs setup
morning                          → Morning briefing
show my tasks                    → List tasks
add Title to my tasks            → Create task (append --priority 5 etc. if you want)
mark Title as done               → Complete a task (by ID or title)
add milk to my grocery list      → Add to a list (creates it if it's new)
what's on my grocery list        → Show a list
set an alarm for 7am             → Create an alarm
remind me to call Mom at 5pm     → Create a reminder
What's the weather?              → Ask a question
Tell me about tomorrow           → Tomorrow preview
```

---

## All Launcher Commands

| Command | What it Does |
|---------|--------------|
| `./run.sh` | Start web server + console (default) |
| `./run.sh chatbot` | Console, non-reload mode |
| `./run.sh cli briefing` | Interactive briefing CLI |
| `./run.sh cli tasks` | Interactive task CLI |
| `./run.sh test all` | Run all tests |
| `./run.sh dev` | Dev shell (auto-managed venv pre-activated) |

---

## Access from Phone

1. Make sure phone is on Tailscale mesh
2. Open browser to: `http://100.117.41.53:5000`
   - Or use: `http://sunshine-m700:5000`
3. Chat with Sunny from anywhere!

---

## Troubleshooting

### Port 5000 already in use?
```bash
# Edit run.sh and change --port 5000 to --port 5001
nano run.sh
./run.sh
# Now access at: http://127.0.0.1:5001
```

### Something broken after an update?
`run.sh` manages its own virtual environment — you never create or activate one yourself. If dependencies get into a bad state, delete the auto-created folder and let the launcher rebuild it:
```bash
rm -rf venv
./run.sh
```

### Update Python packages?
```bash
./run.sh dev
pip install --upgrade -r requirements.txt
exit
```

---

## Next Steps

1. ✓ Run `./run.sh`
2. ✓ Open `http://127.0.0.1:5000` in browser (redirects to `/console`)
3. ✓ Type "morning" to see morning briefing
4. ✓ Type "show my tasks" to see task list
5. ✓ Check the sidebar for live system stats and Google sign-in status
6. ✓ Access from phone over Tailscale

---

## Full Guides

- **Setup & Deployment**: See [[../SETUP_LINUX.md]]
- **Architecture**: See [[./architecture/Mind-Map.md]]
- **Build Timeline**: See [[./phases.md]]
- **Task System**: See [[./TASK_SYSTEM.md]]
- **Lists**: See [[./architecture/lists.md]]
- **Alarms & Reminders**: See [[./architecture/alarms-reminders.md]]
- **Discord Bot Setup**: See [[./architecture/discord-bot.md]]

---

Enjoy! 🌞
