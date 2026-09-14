# Project SUNNY — Linux Setup Guide

Complete setup instructions for Linux (Ubuntu/Debian/Fedora) and macOS.

## Prerequisites

- Linux (Ubuntu 26.04 LTS recommended, Debian, Fedora) or macOS
- Python 3.9+
- Git
- ~500MB disk space

## Quick Setup (2 minutes)

```bash
# Clone the repository (if not already done)
git clone https://github.com/T3R4Bit/Project-SUNNY.git
cd Project-SUNNY

# Make launcher executable
chmod +x run.sh

# Start the app
./run.sh
```

Done! The launcher will:
- Create a virtual environment automatically if one doesn't exist (you never create or activate it yourself)
- Install Python dependencies
- Start the web server
- Serve Sunny's HTTP API on `http://127.0.0.1:5000` (`/` redirects to the standalone `project-dashboard` web UI — Sunny's own console was retired)

## Installation Steps

### 1. Install Python 3.9+

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version # Verify
```

**Fedora/RHEL:**
```bash
sudo dnf install -y python3 python3-venv
python3 --version
```

**macOS (with Homebrew):**
```bash
brew install python3
python3 --version
```

### 2. Voice Support (Optional — /speak and Sunny's persistent voice presence in Discord)

`discord.py` needs the system Opus codec library for voice playback and receive — not something `pip`/`requirements.txt` can install. Skip this if you don't need Discord voice features; every other part of Sunny works fine without it.

**Ubuntu/Debian:**
```bash
sudo apt install -y libopus0
```

Found the hard way (2026-08-20): everything else about live voice conversation — connecting, command registration, Piper synthesis — worked without this installed; only the actual `voice_client.play()` call failed, with `OpusNotLoaded`. See `sunny-vault/docs/architecture/voice-join.md`.

### 3. Clone Repository

```bash
git clone https://github.com/T3R4Bit/Project-SUNNY.git
cd Project-SUNNY
```

### 4. Make Launcher Executable

```bash
chmod +x run.sh
ls -la run.sh # Verify it has 'x' permission
```

### 5. Start the App

```bash
./run.sh
```

First run will:
- Create `venv/` directory automatically (~200MB) — this is handled entirely by `run.sh`, not a manual step
- Install dependencies from `requirements.txt`
- Start FastAPI server on `127.0.0.1:5000`

Every run after the first reuses the existing `venv/` and just reinstalls/updates dependencies quietly.

## Usage

### Start Web Server (Default)
```bash
./run.sh
# Access: http://127.0.0.1:5000
```

### Interactive CLIs
```bash
# Briefing system
./run.sh cli briefing

# Task management
./run.sh cli tasks
```

### Run Tests
```bash
# All tests
./run.sh test all

# Individual tests
./run.sh test briefing
./run.sh test tasks
```

### Development Mode
```bash
# Opens shell with the auto-managed venv pre-activated
./run.sh dev

# Now you can run Python directly
python -c "import sunny_code; print('OK')"
exit # Exit dev mode
```

## Features Available

### Web UI
- Sunny's own console was retired 2026-09-13 — the standalone `project-dashboard`
  app (running alongside Sunny on the same host) now owns the web UI. `/` on
  Sunny redirects there. See that app's own README for what it shows.
- Talk to Sunny via Discord text/voice or `python chat.py` (terminal) — there is
  no browser-based chat anymore. Both route through the same `handle_message()`
  as before, including `setup` for step-by-step instructions on connecting any
  API (weather, Google, Discord).

### Briefing System
- Morning briefing (9 sections)
- Evening briefing (7 sections)
- Q&A engine for custom questions
- Tasks queried live from the Obsidian vault (markdown, not a database); no API key needed. Weather, Google Calendar, and Gmail are real, live data once connected (API key / Google Sign-In). Commute, health, motorsports, and news still have no real API behind them and honestly say "not connected" instead of faking data — no mock data anywhere

### Task Management
- Create: `add Title to my tasks` (append `--tag Category` etc. for precision)
- Update: `mark Title as done`
- Delete: `delete Title`
- Categories are free-form — any `--tag` value works, no fixed list to pick from
- No task IDs shown anywhere — everything's referenced by title
- Filter: By category, status, due date
- Dashboard: View all tasks organized by category
- No command prefix required — plain natural phrasing, deterministic regex parsing, no LLM

### Lists
- Named checkable lists: `add milk to my grocery list`, `what's on my grocery list`, `my lists`
- No name given → falls back to a default "To-Do" list
- Same no-LLM, free-form philosophy as tasks — see `sunny-vault/docs/architecture/lists.md`

### Alarms & Reminders
- `set an alarm for 7am`, `remind me to call Mom at 5pm`, `what alarms are set`, `cancel my 7am alarm`
- Time-based only (no location tracking) — deterministic parsing, no external date library
- Nothing "sounds" without hardware; the only real delivery today is a Discord ping when due — see `sunny-vault/docs/architecture/alarms-reminders.md`

### Discord Bot (Optional)
- Same task/list/alarm/reminder commands as terminal chat (`python chat.py`), typed as plain messages in one dedicated chat channel
- Pinned task dashboard in its own separate, read-only channel (falls back to the chat channel if not configured), auto-refreshes every 5 minutes and on every task change
- Separate 30-second loop posts a ping ("Alarm: ..."/"Reminder: ...") whenever an alarm or reminder comes due, in the chat channel
- Not running unless `DISCORD_BOT_TOKEN` and `DISCORD_CHAT_CHANNEL_ID` are set in `.env` — terminal chat works either way
- Setup steps: `sunny-vault/docs/architecture/discord-bot.md`

### API Endpoints
- `/api/briefing/morning` — Get morning briefing
- `/api/briefing/evening` — Get evening briefing
- `/api/briefing/ask?q=...` — Ask a question
- `/api/tasks/list` — List tasks
- `/api/tasks/command` — Execute task command
- `/api/tasks/dashboard` — Task dashboard
- `/docs` — Interactive API documentation (Swagger)

## Troubleshooting

### "Permission denied" on run.sh
```bash
chmod +x run.sh
./run.sh
```

### Port 5000 already in use
```bash
# Edit run.sh and change port:
nano run.sh
# Change: --port 5000 to --port 5001
./run.sh
# Access: http://127.0.0.1:5001
```

### Python version too old
```bash
# Check version
python3 --version # Need 3.9+
```
If your default `python3` is too old but a newer interpreter is installed (e.g. `python3.11`), edit the `python3 -m venv venv` line near the top of `run.sh` to call that interpreter instead, then let the launcher rebuild everything:
```bash
rm -rf venv
./run.sh
```

### Virtual environment issues
`run.sh` owns the `venv/` directory end-to-end — you never create, activate, or manage it yourself. If something's broken, just delete it and let the launcher rebuild it on the next run:
```bash
rm -rf venv
./run.sh
```

### Dependency installation fails
```bash
# Try manual install
./run.sh dev
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
exit
```

## Deployment to Lenovo Brain

Once tested locally, deploy to the always-on Lenovo mini PC:

```bash
# On Lenovo (via SSH or local terminal)
cd /home/user/Project-SUNNY
./run.sh
```

Create systemd service for auto-start:

```bash
# Create service file
sudo tee /etc/systemd/system/sunny.service > /dev/null <<EOF
[Unit]
Description=Project SUNNY Assistant
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/Project-SUNNY
ExecStart=/home/$USER/Project-SUNNY/run.sh server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable sunny.service
sudo systemctl start sunny.service
sudo systemctl status sunny.service
```

Access from anywhere via Tailscale:
```bash
# From phone or laptop
http://100.117.41.53:5000
# or
http://sunshine-m700:5000
```

### Getting `git pull` Working on the Lenovo

The Lenovo has its own SSH keypair (`~/.ssh/id_ed25519`), but its public key isn't registered anywhere on GitHub yet, so `git pull`/`git fetch` there fail with `Permission denied (publickey)`. To fix it: copy `cat ~/.ssh/id_ed25519.pub` from the Lenovo, then on GitHub go to this repo → **Settings → Deploy keys → Add deploy key**, paste it in (read-only is enough for pulling), and `git pull` will work directly from then on. Until that's done, deploys land by copying the current tracked working tree over SSH instead (`git ls-files | tar -czf - -T - | ssh sunny-lenovo "cd ~/Project-SUNNY && tar -xzf -"` from a machine that already has GitHub push access) — same effect as a pull, just doesn't need the Lenovo to authenticate to GitHub itself.

## Environment Variables

Optional `.env` file for customization:

```bash
# Create .env
cat > .env <<EOF
APP_ENV=production
DEBUG=false
API_HOST=0.0.0.0 # Listen on all interfaces
API_PORT=5000
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF

./run.sh
```

## API Keys & Secrets

All API keys (Claude, OpenWeatherMap, Google Calendar, Discord bot token) live in `.env`, never in code:

- **Never committed** — `.env`, `.env.local`, and `.env.*.local` are all in `.gitignore`. There's no separate `.env.example` in the repo either: the template lives inline in `run.sh`, which writes `.env` from it automatically on first run if the file's missing.
- **File permissions** — `run.sh` runs `chmod 600 .env` automatically on every start, so only the owning user can read it.
- **Never paste a real key into chat, a commit, or an issue** — edit `.env` directly on the machine instead. If a key ever does leak, rotate it at the provider immediately (regenerating invalidates the old one).
- **What's still missing** — Sunny logs a summary at startup of which tracked keys aren't set yet (`sunny_code/components/key_status.py`), and if the Discord bot is connected it posts the same summary once per run — to `DISCORD_WARNINGS_CHANNEL_ID` if set, else the chat channel. Nothing crashes without a key; the affected feature just says "not connected" instead of faking data — see `sunny-vault/log/requests.md` for what's actually being asked for.

## Project Structure

```
Project-SUNNY/
├── run.sh # Main launcher (bash)
├── requirements.txt # Python dependencies
├── .env # Your local secrets (gitignored, chmod 600; auto-created by run.sh from its built-in template)
├── sunny_code/
│ ├── __init__.py
│ ├── config.py # Configuration management
│ ├── logging_config.py # Logging setup
│ ├── main.py # FastAPI app + Discord bot startup
│ └── components/
│ ├── briefing.py # Briefing engine (real tasks, honest gaps elsewhere)
│ ├── briefing_api.py
│ ├── data_sources.py # Which data sources are real vs unconfigured
│ ├── request_log.py # Logs unfulfilled requests to sunny-vault/log/requests.md
│ ├── key_status.py # Startup summary of missing API keys
│ ├── setup_guides.py # "setup <api>" step-by-step instructions (chat command)
│ ├── google_auth.py # Google OAuth sign-in flow + token storage/refresh
│ ├── google_routes.py # /auth/google/* routes
│ ├── google_calendar.py # Live Calendar reads
│ ├── google_gmail.py # Live Gmail reads
│ ├── tasks_db.py # Task database
│ ├── tasks_engine.py
│ ├── tasks_parser.py # Natural language + legacy !task parsing
│ ├── tasks_api.py
│ ├── lists_db.py # List database (lists + list_items)
│ ├── lists_engine.py
│ ├── lists_parser.py # Natural language parsing for lists
│ ├── scheduled_db.py # Alarm/reminder database
│ ├── scheduled_engine.py
│ ├── scheduled_parser.py # Natural language parsing for alarms/reminders
│ ├── time_parse.py # Deterministic time/recurrence parsing (no library)
│ ├── device.py # Maps a session_id to source: discord | pi | api
│ ├── assistant.py # Shared message routing (terminal chat + Discord bot)
│ ├── discord_bot.py # Discord bot — tasks/lists/alarms, pinned dashboard, due-item pings
│ ├── dashboard.py # Dashboard JSON API (/api/dashboard/*)
│ └── dashboard_data_routes.py # Structured Calendar/Gmail API for external dashboards
├── test_*.py # Test files
├── sunny-vault/ # Documentation + Obsidian vault
│ ├── log/requests.md # What Sunny couldn't fulfill with real data (auto-generated)
│ └── docs/
│ ├── architecture/
│ ├── phases.md
│ └── TASK_SYSTEM.md
├── venv/ # Virtual environment (auto-created)
└── logs/ # Log files (auto-created)
```

## Next Steps

1. Run `./run.sh` to start
2. Run `python chat.py` (or use Discord) and type "morning" to see briefing
3. Type "show my tasks" to see task list
4. Deploy `project-dashboard` alongside Sunny for a web UI (see its own README)
5. Deploy to Lenovo brain for 24/7 access
6. Access from phone over Tailscale

## Support

- Documentation: `sunny-vault/docs/`
- Build phases: `sunny-vault/docs/phases.md`
- Architecture: `sunny-vault/docs/architecture/`
- GitHub: https://github.com/T3R4Bit/Project-SUNNY

Happy coding!
