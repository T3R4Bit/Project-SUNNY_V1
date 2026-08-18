---
id: sunny-source-structure
type: documentation
status: active
created: 2026-08-18
tags: [source, structure, python, project-layout]
---

# Project SUNNY — Source Code Structure

Phase 0 bootstrap: Core Python package with logging, config, dashboard, and priority queue.

```
Project-SUNNY/
├── sunny/                 # Main Python package
│   ├── __init__.py       # Package metadata
│   ├── main.py           # Entry point (systemd starts this)
│   ├── logging.py        # Structured logging (file + console)
│   ├── config.py         # Configuration and secrets (from .env)
│   ├── dashboard.py      # FastAPI web UI (FastAPI app + endpoints)
│   ├── priority_queue.py # Request priority scheduling (async queue)
│   └── (future modules)
│
├── systemd/
│   └── sunny.service     # Systemd unit (Restart=always)
│
├── logs/                 # Rotating log files (auto-created)
│   └── YYYY-MM-DD.log
│
├── sunny-vault/          # Obsidian vault (staging/archive/log/state)
│
├── requirements.txt      # Python dependencies
├── .env.example         # Secrets template (copy to .env)
├── .gitignore           # Git exclusions (venv, logs, .env, *.db)
└── README.md            # Project overview
```

---

## What Each Module Does

### `logging.py`
- Structured logging to console + rotating file handler
- Logs rotate daily, keeps 30 days
- All messages include: timestamp, level, module name, message

**Usage**:
```python
from sunny.logging import logger
logger.info("Something happened")
```

### `config.py`
- Loads secrets from `.env` file using `python-dotenv`
- Provides `Config` class with all settings
- Validates required secrets at startup

**Usage**:
```python
from sunny.config import Config
api_key = Config.CLAUDE_API_KEY
```

### `dashboard.py`
- FastAPI web server (runs on Tailscale IP:5000)
- SQLite database for metrics (create/read)
- Endpoints for health, resources, spending, alerts
- Simple HTML dashboard (auto-refreshes every 60s)

**Usage**:
```python
uvicorn sunny.dashboard:app --host 100.1.1.2 --port 5000
```

### `priority_queue.py`
- Async priority queue for managing concurrent requests
- Foreground requests (phone, active clock) preempt background tasks
- 4 worker threads processing requests in priority order

**Usage**:
```python
queue = PriorityQueue(max_workers=4)
await queue.add(
    request_id="clock-001",
    surface=InputSurface.CLOCK,
    handler=my_async_handler,
    priority=Priority.FOREGROUND,
)
```

### `main.py`
- Starts the Sunny system
- Initializes logger, config, database, queue
- Entry point for systemd service

**Usage**:
```bash
python -m sunny.main
```

---

## Getting Started (Local Development)

### 1. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set Up Secrets
```bash
cp .env.example .env
# Edit .env with your actual API keys
```

### 4. Test Dashboard
```bash
python -m uvicorn sunny.dashboard:app --reload --host 127.0.0.1 --port 5000
# Open http://localhost:5000
```

### 5. Test Main Entry Point
```bash
python -m sunny.main
# Should log startup messages and wait for requests
```

---

## Deployment to Lenovo (Systemd)

### On the Lenovo Mini PC:

1. **Create user and clone repo**:
   ```bash
   sudo useradd -m sunny
   sudo -u sunny git clone <your-repo> /home/sunny/Project-SUNNY
   cd /home/sunny/Project-SUNNY
   ```

2. **Set up venv**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Copy secrets**:
   ```bash
   cp .env.example .env
   # Edit .env with actual secrets
   ```

4. **Install systemd service**:
   ```bash
   sudo cp systemd/sunny.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable sunny
   sudo systemctl start sunny
   ```

5. **Check status**:
   ```bash
   sudo systemctl status sunny
   sudo journalctl -u sunny -f  # Follow logs
   ```

---

## Next Steps (Phase 1+)

- **Phase 1**: Network config (Tailscale integration)
- **Phase 2**: Briefing engine (calendar, weather, task fetching)
- **Phase 5**: Phone interface (Twilio webhook + LLM routing)
- **Later**: Clock hardware (ESP32, wake word, voice I/O)

See `sunny-vault/docs/phases.md` for full timeline.
