# 🐧 Project SUNNY — Linux Setup Guide

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
- ✓ Create a virtual environment automatically if one doesn't exist (you never create or activate it yourself)
- ✓ Install Python dependencies
- ✓ Start the web server
- ✓ Serve the chatbot at `http://127.0.0.1:5000/chatbot` (`http://127.0.0.1:5000` redirects there)

## Installation Steps

### 1. Install Python 3.9+

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version  # Verify
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

### 2. Clone Repository

```bash
git clone https://github.com/T3R4Bit/Project-SUNNY.git
cd Project-SUNNY
```

### 3. Make Launcher Executable

```bash
chmod +x run.sh
ls -la run.sh  # Verify it has 'x' permission
```

### 4. Start the App

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

### Start Just Chatbot
```bash
./run.sh chatbot
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
python -c "import sunny; print('OK')"
exit  # Exit dev mode
```

## Features Available

### 🤖 Web Chatbot UI
- Chat interface at `/chatbot` (`/` redirects there)
- Talk to the briefing engine and task system
- Access from phone over Tailscale
- No installation needed on phone

### 📊 System Console
- Live CPU, RAM, disk, network, and temperature stats at `/console`
- Auto-refreshes every 2 seconds

### 📋 Briefing System
- Morning briefing (9 sections)
- Evening briefing (7 sections)
- Q&A engine for custom questions
- Mock data built-in (no API keys needed for testing)

### ✅ Task Management
- Create: `add Title to my tasks` (append `--tag School --priority 5` etc. for precision)
- Update: `mark abc123 as done` (or by title: `mark Title as done`)
- Delete: `delete abc123` (or by title)
- Filter: By tag, status, priority, due date
- Dashboard: View all tasks organized by category
- No command prefix required — plain natural phrasing, deterministic regex parsing, no LLM

### 🤖 Discord Bot (Optional)
- Same task commands as the web chatbot, typed as plain messages in one dedicated channel
- Pinned dashboard message, auto-refreshes every 5 minutes, 🔄 reaction for instant refresh
- Not running unless `DISCORD_BOT_TOKEN` and `DISCORD_TASKS_CHANNEL_ID` are set in `.env` — web chatbot works either way
- Setup steps: `sunny-vault/docs/architecture/discord-bot.md`

### 📊 API Endpoints
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
python3 --version  # Need 3.9+
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

## Environment Variables

Optional `.env` file for customization:

```bash
# Create .env
cat > .env <<EOF
APP_ENV=production
DEBUG=false
API_HOST=0.0.0.0  # Listen on all interfaces
API_PORT=5000
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF

./run.sh
```

## API Keys & Secrets

All API keys (Claude, OpenWeatherMap, Google Calendar, Discord bot token) live in `.env`, never in code:

- **Never committed** — `.env`, `.env.local`, and `.env.*.local` are all in `.gitignore`. Only `.env.example` (no real values) is tracked.
- **File permissions** — `run.sh` runs `chmod 600 .env` automatically on every start, so only the owning user can read it.
- **Never paste a real key into chat, a commit, or an issue** — edit `.env` directly on the machine instead. If a key ever does leak, rotate it at the provider immediately (regenerating invalidates the old one).
- **What's still missing** — Sunny logs a summary at startup of which tracked keys aren't set yet (`sunny/components/key_status.py`), and if the Discord bot is connected it posts the same summary to the tasks channel once per run. Nothing crashes without a key; the affected feature just says "not connected" instead of faking data — see `sunny-vault/log/requests.md` for what's actually being asked for.

## Project Structure

```
Project-SUNNY/
├── run.sh                  # Main launcher (bash)
├── requirements.txt        # Python dependencies
├── .env                    # Your local secrets (gitignored, chmod 600)
├── .env.example            # Template — no real values
├── sunny/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── logging_config.py  # Logging setup
│   ├── main.py            # FastAPI app + Discord bot startup
│   └── components/
│       ├── briefing.py         # Briefing engine (real tasks, honest gaps elsewhere)
│       ├── briefing_api.py
│       ├── briefing_data.py    # Mock data structures (unused by briefing.py directly)
│       ├── data_sources.py     # Which data sources are real vs unconfigured
│       ├── request_log.py      # Logs unfulfilled requests to sunny-vault/log/requests.md
│       ├── key_status.py       # Startup summary of missing API keys
│       ├── tasks_db.py         # Task database
│       ├── tasks_engine.py
│       ├── tasks_parser.py     # Natural language + legacy !task parsing
│       ├── tasks_api.py
│       ├── assistant.py        # Shared message routing (web chatbot + Discord bot)
│       ├── discord_bot.py      # Discord bot — tasks channel + pinned dashboard
│       ├── dashboard.py        # Dashboard JSON API
│       ├── console_stats.py    # /console system stats page
│       └── chatbot_ui.py       # Web UI (/chatbot, / redirects there)
├── test_*.py              # Test files
├── sunny-vault/           # Documentation + Obsidian vault
│   ├── log/requests.md    # What Sunny couldn't fulfill with real data (auto-generated)
│   └── docs/
│       ├── architecture/
│       ├── phases.md
│       └── TASK_SYSTEM.md
├── venv/                  # Virtual environment (auto-created)
└── logs/                  # Log files (auto-created)
```

## Next Steps

1. ✓ Run `./run.sh` to start
2. ✓ Open `http://127.0.0.1:5000` in browser
3. ✓ Type "morning" to see briefing
4. ✓ Type "show my tasks" to see task list
5. ✓ Check `/console` for live system stats
6. ✓ Deploy to Lenovo brain for 24/7 access
7. ✓ Access from phone over Tailscale

## Support

- Documentation: `sunny-vault/docs/`
- Build phases: `sunny-vault/docs/phases.md`
- Architecture: `sunny-vault/docs/architecture/`
- GitHub: https://github.com/T3R4Bit/Project-SUNNY

Happy coding! 🌞
