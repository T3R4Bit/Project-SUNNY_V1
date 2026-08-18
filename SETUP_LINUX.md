# 🐧 Project SUNNY — Linux Setup Guide

Complete setup instructions for Linux (Ubuntu/Debian/Fedora) and macOS.

## Prerequisites

- Linux (Ubuntu 20.04+, Debian, Fedora) or macOS
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
- ✓ Create virtual environment if needed
- ✓ Install Python dependencies
- ✓ Start the web server
- ✓ Open chatbot at `http://127.0.0.1:5000/chatbot`

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
- Create `venv/` directory (~200MB)
- Install dependencies from `requirements.txt`
- Start FastAPI server on `127.0.0.1:5000`

## Usage

### Start Web Server (Default)
```bash
./run.sh
# Access: http://127.0.0.1:5000/chatbot
```

### Start Just Chatbot
```bash
./run.sh chatbot
# Access: http://127.0.0.1:5000/chatbot
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
# Opens shell with venv pre-activated
./run.sh dev

# Now you can run Python directly
python -c "import sunny; print('OK')"
exit  # Exit dev mode
```

## Features Available

### 🤖 Web Chatbot UI
- Beautiful web interface
- Chat with AI assistant
- Access from phone over Tailscale
- No installation needed on phone

### 📋 Briefing System
- Morning briefing (9 sections)
- Evening briefing (7 sections)
- Q&A engine for custom questions
- Mock data built-in (no API keys needed for testing)

### ✅ Task Management
- Create: `!task add "Title" --tag School --priority 5`
- Update: `!task abc123 status done`
- Delete: `!task abc123 delete`
- Filter: By tag, status, priority, due date
- Dashboard: View all tasks organized by category

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
# Access: http://127.0.0.1:5001/chatbot
```

### Python version too old
```bash
# Check version
python3 --version  # Need 3.9+

# Use python3.11 if available
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn sunny.main:app --host 127.0.0.1 --port 5000
```

### Virtual environment issues
```bash
# Remove and recreate
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
http://100.117.41.53:5000/chatbot
# or
http://sunshine-m700:5000/chatbot
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

## Project Structure

```
Project-SUNNY/
├── run.sh                  # Main launcher (bash)
├── requirements.txt        # Python dependencies
├── sunny/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── logging_config.py  # Logging setup
│   ├── main.py            # FastAPI app
│   └── components/
│       ├── briefing.py    # Briefing engine
│       ├── briefing_api.py
│       ├── briefing_data.py
│       ├── tasks_db.py    # Task database
│       ├── tasks_engine.py
│       ├── tasks_parser.py
│       ├── tasks_api.py
│       ├── dashboard.py   # Dashboard
│       └── chatbot_ui.py  # Web UI
├── test_*.py              # Test files
├── sunny-vault/           # Documentation
│   └── docs/
│       ├── architecture/
│       ├── phases.md
│       └── TASK_SYSTEM.md
├── venv/                  # Virtual environment (auto-created)
└── logs/                  # Log files (auto-created)
```

## Next Steps

1. ✓ Run `./run.sh` to start
2. ✓ Open `http://127.0.0.1:5000/chatbot` in browser
3. ✓ Type "morning" to see briefing
4. ✓ Type "!tasks" to see task list
5. ✓ Deploy to Lenovo brain for 24/7 access
6. ✓ Access from phone over Tailscale

## Support

- Documentation: `sunny-vault/docs/`
- Build phases: `sunny-vault/docs/phases.md`
- Architecture: `sunny-vault/docs/architecture/`
- GitHub: https://github.com/T3R4Bit/Project-SUNNY

Happy coding! 🌞
