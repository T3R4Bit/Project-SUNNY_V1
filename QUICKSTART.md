# 🌞 Project SUNNY — Quick Start Guide

No need to manually activate venv anymore! Use these commands to get started.

## Windows PowerShell

```powershell
# Start web server + chatbot UI (default)
.\run.ps1

# Start chatbot web UI only
.\run.ps1 chatbot

# Test systems
.\run.ps1 test all
.\run.ps1 test briefing
.\run.ps1 test tasks

# Interactive CLIs
.\run.ps1 cli briefing
.\run.ps1 cli tasks

# Dev shell (venv pre-activated)
.\run.ps1 dev
```

## Windows Command Prompt (cmd.exe)

```cmd
REM Start web server
run.bat

REM Start chatbot
run.bat chatbot

REM Run tests
run.bat test-briefing
run.bat test-tasks
run.bat test-all

REM Interactive CLIs
run.bat cli-briefing
run.bat cli-tasks

REM Dev mode
run.bat dev
```

## What Each Command Does

### `.\run.ps1` or `run.bat`
Starts FastAPI server with all endpoints:
- Web server: `http://127.0.0.1:5000`
- **Chatbot UI**: `http://127.0.0.1:5000/chatbot` ← Try this! 🤖
- API Docs: `http://127.0.0.1:5000/docs`
- Briefing API: `/api/briefing/morning`, `/api/briefing/evening`
- Tasks API: `/api/tasks/list`, `/api/tasks/command`

### `.\run.ps1 chatbot`
Starts just the web server. Open browser to `http://127.0.0.1:5000/chatbot`

**Try asking in the chatbot:**
- "morning" → Get morning briefing
- "!tasks" → List all tasks
- "!task add \"Fix bug\" --tag General --priority 5" → Create task
- "What's the weather?" → Weather info
- "Tell me about my day" → Briefing summary

### `.\run.ps1 cli briefing`
Interactive CLI for testing briefing engine:
```
You: morning
You: What's the weather?
You: Tell me about my tasks
You: exit
```

### `.\run.ps1 cli tasks`
Interactive CLI for testing task system:
```
You: !task add "Study physics" --tag School --priority 5 --due 2026-08-20
You: !tasks
You: !task abc123 status done
You: exit
```

### `.\run.ps1 test all`
Runs complete test suite for briefing and tasks systems:
- Database operations (CRUD)
- Command parsing
- Engine execution
- HTTP API endpoints

## After Git Pull

No need for manual setup! Just run:
```powershell
.\run.ps1
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
- Edit `run.ps1` line: `--port 5001` (or any free port)
- Then access at `http://127.0.0.1:5001/chatbot`

**venv issues?**
```powershell
Remove-Item venv -Recurse
.\run.ps1
```

**Need to update Python packages?**
```powershell
.\run.ps1 dev
pip install --upgrade -r requirements.txt
exit
```

## File Organization

```
D:\Project-SUNNY\
├── run.ps1              ← Use this (PowerShell)
├── run.bat              ← Or this (Command Prompt)
├── sunny/               ← Main Python package
├── test_*.py            ← Test files
└── requirements.txt     ← Python dependencies
```

## Next Steps

1. Try the chatbot: `.\run.ps1 chatbot`
2. Open: `http://127.0.0.1:5000/chatbot`
3. Type: `morning` and see morning briefing
4. Type: `!tasks` and see your tasks
5. Access from phone over Tailscale: `http://100.117.41.53:5000/chatbot`

Enjoy! 🌞
