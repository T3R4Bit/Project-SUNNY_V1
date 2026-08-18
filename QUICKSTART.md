# 🌞 Project SUNNY — Quick Start Guide

No need to manually activate venv anymore! Use the bash launcher.

## Linux / macOS / WSL

```bash
# Make executable (first time only)
chmod +x run.sh

# Start web server + chatbot UI (default)
./run.sh

# Start chatbot web UI only
./run.sh chatbot

# Test systems
./run.sh test all
./run.sh test briefing
./run.sh test tasks

# Interactive CLIs
./run.sh cli briefing
./run.sh cli tasks

# Dev shell (venv pre-activated)
./run.sh dev
```

## What Each Command Does

### `./run.sh`
Starts FastAPI server with all endpoints:
- Web server: `http://127.0.0.1:5000`
- **Chatbot UI**: `http://127.0.0.1:5000/chatbot` ← Try this! 🤖
- API Docs: `http://127.0.0.1:5000/docs`
- Briefing API: `/api/briefing/morning`, `/api/briefing/evening`
- Tasks API: `/api/tasks/list`, `/api/tasks/command`

### `./run.sh chatbot`
Starts just the web server. Open browser to `http://127.0.0.1:5000/chatbot`

**Try asking in the chatbot:**
- "morning" → Get morning briefing
- "!tasks" → List all tasks
- "!task add \"Fix bug\" --tag General --priority 5" → Create task
- "What's the weather?" → Weather info
- "Tell me about my day" → Briefing summary

### `./run.sh cli briefing`
Interactive CLI for testing briefing engine:
```
You: morning
You: What's the weather?
You: Tell me about my tasks
You: exit
```

### `./run.sh cli tasks`
Interactive CLI for testing task system:
```
You: !task add "Study physics" --tag School --priority 5 --due 2026-08-20
You: !tasks
You: !task abc123 status done
You: exit
```

### `./run.sh test all`
Runs complete test suite for briefing and tasks systems:
- Database operations (CRUD)
- Command parsing
- Engine execution
- HTTP API endpoints

## After Git Pull

No need for manual setup! Just run:
```bash
./run.sh
```

The launcher automatically:
- Creates venv if missing
- Activates venv
- Installs/updates dependencies
- Starts the app

## Accessing Over Tailscale

Once the server is running, access from your phone:

1. Make sure phone is on Tailscale mesh
2. Open browser to: `http://100.117.41.53:5000/chatbot`
   (Or use `http://sunshine-m700:5000/chatbot`)
3. Chat with the AI assistant from anywhere!

## Features Available

### 🤖 Chatbot Web UI
- Chat interface in browser
- Works over Tailscale (access from phone)
- Commands: "morning", "!tasks", questions, task commands

### 📋 Briefing System
- Morning briefing (9 sections)
- Evening briefing (7 sections)
- Q&A: Ask anything (weather, calendar, tasks, etc.)
- No API keys needed for testing (uses mock data)

### ✅ Task Management
- Create: `!task add "Title" --tag School --priority 5`
- Update: `!task abc123 status done`
- Delete: `!task abc123 delete`
- List: `!tasks`, `!tasks --tag School`, `!tasks --priority 4`
- Tags: School, Motorsports, General, Project Ideas

### 📊 Dashboard
- Token spending tracker
- Service health monitor
- System resources (CPU, RAM, disk)
- Task statistics

## Troubleshooting

**Port 5000 already in use?**
- Edit `run.sh` line: `--port 5001` (or any free port)
- Then access at `http://127.0.0.1:5001/chatbot`

**venv issues?**
```bash
rm -rf venv
./run.sh
```

**Need to update Python packages?**
```bash
./run.sh dev
pip install --upgrade -r requirements.txt
exit
```

## File Organization

```
/path/to/Project-SUNNY/
├── run.sh               ← Main launcher (bash)
├── sunny/               ← Main Python package
├── test_*.py            ← Test files
└── requirements.txt     ← Python dependencies
```

## Next Steps

1. Make executable: `chmod +x run.sh`
2. Try the chatbot: `./run.sh chatbot`
3. Open: `http://127.0.0.1:5000/chatbot`
4. Type: `morning` and see morning briefing
5. Type: `!tasks` and see your tasks
6. Access from phone over Tailscale: `http://100.117.41.53:5000/chatbot`

Enjoy! 🌞
