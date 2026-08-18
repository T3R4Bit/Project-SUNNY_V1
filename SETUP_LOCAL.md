# Local Development Setup

Run Project SUNNY locally on your workstation before deploying to the Lenovo brain.

## Prerequisites

- Python 3.9+
- PowerShell or bash terminal
- Virtual environment (venv)

## Setup Steps

### 1. Create Virtual Environment

```powershell
# Navigate to project directory
cd D:\Project-SUNNY

# Create venv
python -m venv venv

# Activate venv
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Environment

```powershell
# Copy example config
cp .env.example .env

# Edit .env with your API keys
notepad .env
```

Required API keys for Phase 2:
- `CLAUDE_API_KEY` — from Anthropic console
- `OPENWEATHERMAP_API_KEY` — from OpenWeatherMap (free tier ok)
- `GOOGLE_CALENDAR_API_KEY` — if using Google Calendar

For now, these can stay empty; defaults will mock the data.

### 4. Run Locally

```powershell
# Start the application
python -m sunny.main

# Or with uvicorn directly
uvicorn sunny.main:SunnyCore.app --reload --host 127.0.0.1 --port 5000
```

The API will be available at: `http://127.0.0.1:5000/`

### 5. Test Endpoints

```powershell
# Health check
curl http://127.0.0.1:5000/health

# Dashboard status
curl http://127.0.0.1:5000/api/dashboard/status

# Record a metric
curl -X POST "http://127.0.0.1:5000/api/dashboard/metrics/record?cpu=45&ram=60&disk=50"
```

## Project Structure

```
D:\Project-SUNNY/
├── sunny/                 # Main package
│   ├── __init__.py
│   ├── config.py         # Configuration (pydantic-settings)
│   ├── logging_config.py # Logging setup
│   ├── main.py           # Entry point
│   └── components/       # Modular features
│       ├── dashboard.py  # API endpoints + DB
│       ├── briefing.py   # Briefing engine (Phase 2)
│       ├── voice_io.py   # Voice input/output (Phase 4)
│       └── ...
├── logs/                 # Log output (auto-created)
├── .env                  # Local config (DO NOT commit)
├── .env.example          # Example config
├── requirements.txt      # Python dependencies
└── SETUP_LOCAL.md        # This file
```

## Development Workflow

1. **Make changes** — Edit files in `sunny/`
2. **Test locally** — `python -m sunny.main`
3. **Commit** — `git add -A && git commit -m "..."`
4. **Push to Lenovo** — Later, via git push or scp

## Next Steps

After confirming this runs locally, we'll:
- **Phase 2**: Integrate Calendar API, Weather API, hardcoded templates
- **Phase 3**: Add voice output (TTS) routes
- **Phase 4**: Add voice input (STT) routes
- **Deploy**: Push to Lenovo, systemd integration

## Troubleshooting

**Import errors?**
```powershell
# Ensure venv is activated
.\venv\Scripts\Activate.ps1

# Reinstall dependencies
pip install -r requirements.txt
```

**Port already in use?**
```powershell
# Change API_PORT in .env
API_PORT=5001
```

**Database errors?**
```powershell
# Delete and recreate
rm sunny.db
python -m sunny.main
```
