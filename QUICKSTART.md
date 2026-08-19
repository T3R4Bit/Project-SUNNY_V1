# 🌞 Project SUNNY — Quick Start

Get started in 30 seconds.

## 1. Make Executable
```bash
chmod +x run.sh
```

## 2. Run
```bash
./run.sh
```

**Done!** Server starts at `http://127.0.0.1:5000`, which redirects to the console at `http://127.0.0.1:5000/console`

No manual Python setup needed — `run.sh` creates and manages its own virtual environment automatically on first run.

## Commands

```bash
./run.sh                   # Start web server (default)
./run.sh chatbot           # Console, non-reload mode
./run.sh cli briefing      # Interactive briefing CLI
./run.sh cli tasks         # Interactive task CLI
./run.sh test all          # Run all tests
./run.sh dev               # Dev shell (auto-managed venv pre-activated)
```

## Try in the Console

```
help                       → What Sunny can do
setup                      → What's connected, what needs setup
morning                    → Morning briefing
show my tasks              → List tasks
add Title to my tasks      → Create task
mark Title as done         → Complete a task
add milk to my grocery list → Add to a list (creates it if new)
what's on my grocery list  → Show a list
set an alarm for 7am       → Create an alarm
remind me to call Mom at 5pm → Create a reminder
What's the weather?        → Weather info
```

## Access from Phone

1. Phone on Tailscale mesh
2. Open: `http://100.117.41.53:5000`
   (or `http://sunshine-m700:5000`)

## Troubleshooting

**Port in use?**
```bash
nano run.sh              # Edit file
# Change: --port 5000 to --port 5001
./run.sh
```

**Something broken after an update?**
`run.sh` manages its own virtual environment — you never create or activate it yourself. If dependencies get into a bad state, just delete the auto-created folder and let the launcher rebuild it:
```bash
rm -rf venv
./run.sh
```

**Update packages?**
```bash
./run.sh dev
pip install --upgrade -r requirements.txt
exit
```

## Full Setup

See [SETUP_LINUX.md](SETUP_LINUX.md) for complete installation and deployment guide.

Enjoy! 🌞
