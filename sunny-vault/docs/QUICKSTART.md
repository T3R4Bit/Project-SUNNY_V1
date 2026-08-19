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

Server starts automatically at: **`http://127.0.0.1:5000`**

No manual Python environment setup required — `run.sh` creates and manages its own virtual environment automatically on first run, and reuses it on every run after.

---

## What You Get

### Chatbot Web UI
- Console-style chat interface at the site root
- Talk to briefing engine and task system
- Works over Tailscale (access from phone)

### System Console
- Live CPU, RAM, disk, network, and temperature stats
- Available at `/console`

### Briefing System
- Morning briefing (9 sections)
- Evening briefing (7 sections)
- Q&A engine (ask anything)

### Task Management
- Create, update, delete tasks
- Filter by tag, status, priority
- Hardcoded commands (no LLM parsing)

---

## Try These Commands

In the chatbot, type:

```
morning                          → Morning briefing
!tasks                           → List tasks
!task add "Title" --priority 5  → Create task
What's the weather?              → Ask a question
Tell me about tomorrow           → Tomorrow preview
```

---

## All Launcher Commands

| Command | What it Does |
|---------|--------------|
| `./run.sh` | Start web server + chatbot (default) |
| `./run.sh chatbot` | Chatbot UI only |
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
2. ✓ Open `http://127.0.0.1:5000` in browser
3. ✓ Type "morning" to see morning briefing
4. ✓ Type "!tasks" to see task list
5. ✓ Check `/console` for live system stats
6. ✓ Access from phone over Tailscale

---

## Full Guides

- **Setup & Deployment**: See [[../SETUP_LINUX.md]]
- **Architecture**: See [[./architecture/index.md]]
- **Build Timeline**: See [[./phases.md]]
- **Task System**: See [[./TASK_SYSTEM.md]]

---

Enjoy! 🌞
