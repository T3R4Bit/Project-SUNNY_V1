#!/bin/bash
# Project SUNNY — Auto-launch with venv (Bash version)
# Usage: ./run.sh [command]
# Examples:
# ./run.sh Start web server (default) — this is what systemd runs
# ./run.sh reload Same, but with auto-reload on file changes — local dev only
# ./run.sh chatbot Alias for the default server (kept for old muscle memory)
# ./run.sh chat Terminal chat — full assistant, no web server needed
# ./run.sh cli briefing Start briefing CLI
# ./run.sh cli tasks Start tasks CLI
# ./run.sh test briefing Run briefing tests
# ./run.sh test tasks Run task tests

set -e

# Unbuffered stdout/stderr — Python block-buffers by default when stdout isn't
# a tty (true under systemd), which can delay or hide log lines by minutes.
export PYTHONUNBUFFERED=1

COMMAND="${1:-server}"
SUBCOMMAND="${2:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Check if venv exists
if [ ! -f "venv/bin/activate" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}Virtual environment created${NC}"
fi

# Activate venv
source venv/bin/activate

# First run (or a fresh pull — .env is gitignored, so git never creates or
# updates it): write .env from the template below so Sunny has something to
# read. The template lives here, not in a separate .env.example file, so
# .env is the only config file that ever exists on disk.
if [ ! -f ".env" ]; then
    cat > ".env" <<'ENV_TEMPLATE'
# Project SUNNY Configuration — fill in real values below

# App
APP_ENV=development
DEBUG=true
APP_NAME="Project SUNNY"

# APIs (get from respective services)
CLAUDE_API_KEY=sk-ant-...
OPENWEATHERMAP_API_KEY=...
# Optional fallback only — set your real location on /console (LOCATION card)
# instead, it saves instantly with no restart. See
# sunny-vault/docs/architecture/location.md. Format if you do set it here:
# "City,State,CountryCode" — e.g. Detroit,MI,US (state code only applies to US)
WEATHER_LOCATION=...

# Optional — free/self-hosted phone location via OwnTracks (see "setup gps").
# Blank means the /api/location/owntracks endpoint accepts reports with no
# auth at all (fine for personal use over Tailscale).
OWNTRACKS_SHARED_SECRET=

# Google Sign-In (OAuth 2.0) — powers Calendar + Gmail (read-only).
# Setup steps: sunny-vault/docs/architecture/google-integration.md
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://100.117.41.53:5000/auth/google/callback

# Spotify (OAuth 2.0) — powers voice playback control. Requires Premium.
# Spotify requires HTTPS for the redirect URI except literal 127.0.0.1, so
# this needs the same Tailscale-issued cert as Google's TLS_PORT (5443).
# Setup steps: sunny-vault/docs/architecture/spotify-integration.md
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_OAUTH_REDIRECT_URI=https://sunshine-m700.wahoo-sidewinder.ts.net:5443/auth/spotify/callback

# Discord bot — leave token/chat-channel blank to run without the bot (console
# chat still works). Chat channel is the only one commands are read from.
# See sunny-vault/docs/architecture/discord-bot.md for setup steps
DISCORD_BOT_TOKEN=
DISCORD_CHAT_CHANNEL_ID=
# Optional — a separate, read-only home for the pinned task dashboard so it
# doesn't get buried in a busy chat channel. Falls back to the chat channel
# above if left blank (nothing breaks either way).
DISCORD_TASKS_CHANNEL_ID=
# Optional output-only channels — leave blank to keep everything posting to
# the chat channel above instead (nothing breaks either way)
DISCORD_BRIEFINGS_CHANNEL_ID=
DISCORD_WARNINGS_CHANNEL_ID=
DISCORD_TASK_UPDATES_CHANNEL_ID=
DISCORD_HEALTH_CHANNEL_ID=
DISCORD_REMINDERS_CHANNEL_ID=
# Optional — a voice channel for Sunny to stay connected to persistently
# (say "Hey Sunny" before each request, same as before). Leave blank to skip
# voice presence entirely; toggle on/off later with /service voice_join.
DISCORD_VOICE_CHANNEL_ID=

# Network (will bind to this on Lenovo in production)
TAILSCALE_IP=100.117.41.53
API_PORT=5000
API_HOST=127.0.0.1

# Spending caps
DAILY_SPEND_CAP=20.0
MONTHLY_SPEND_CAP=100.0

# Weekly system health check (Sunday 4am — see sunny-vault/docs/architecture/
# health-check.md). Needs a real IANA name (not "EST"/"PST" abbreviations).
LOCAL_TIMEZONE=America/New_York
# Optional, hand-maintained key expiry dates (YYYY-MM-DD) — the health check
# warns you a week before any of these. Blank = skip that key's check; none
# of these providers expose real expiration dates via API.
CLAUDE_API_KEY_EXPIRES=
OPENWEATHERMAP_API_KEY_EXPIRES=
DISCORD_BOT_TOKEN_EXPIRES=
GOOGLE_CLIENT_SECRET_EXPIRES=

# Piper TTS (/speak in Discord) — free, local, no API key needed. Model
# downloads automatically on first use. Leave PIPER_VOICE at the default
# unless you want a different voice (see sunny-vault/docs/architecture/tts-piper.md).
PIPER_VOICE=en_US-lessac-medium
# Optional tuning — leave blank for the voice's own defaults. See
# tts-piper.md's "Tuning Piper's Voice" for what each does and where to start.
PIPER_LENGTH_SCALE=
PIPER_NOISE_SCALE=
PIPER_NOISE_W_SCALE=
PIPER_SPEAKER_ID=

# Vosk STT (Sunny's persistent Discord voice presence) — free, local, no
# API key needed. Model downloads automatically on first use. See
# sunny-vault/docs/architecture/voice-join.md.
VOSK_LANG=en-us
# Specific model by name, bigger vocabulary than VOSK_LANG's small default.
# Leave blank (small model) — vosk-model-en-us-0.22-lgraph crashes voice
# outright (a real Kaldi assertion failure inside its own incremental
# lattice decoder, not fixable from this app — see config.py and
# sunny-vault/docs/architecture/voice-join.md). If accuracy ever needs
# revisiting, try vosk-model-en-us-0.22 (the non-"-lgraph" big model,
# ~1.8GB) instead, not the lgraph one.
VOSK_MODEL_NAME=

# LLM freeform-conversation tuning — for genuinely open-ended questions
# nothing else can answer (see briefing.py's custom_briefing()). The
# actual behavior/tone/persona knob is the system prompt itself:
# sunny-vault/docs/instructions/general-chat.md, hand-editable, no
# restart needed. These three are optional and take effect on the very
# next call, also no restart needed.
LLM_CHAT_MODEL=haiku
# haiku (fast/cheap), sonnet (more capable, slower/pricier), opus
# (rarely worth it here) — see llm_client.py's MODELS dict.
LLM_CHAT_MAX_TOKENS=300
# Hard cap on reply length — kept short since these are meant to be
# brief and are often spoken aloud.
LLM_CHAT_TEMPERATURE=
# 0.0 = deterministic, 1.0 = Anthropic's own default, higher = more
# varied/less literal. Blank leaves it unset (the API's own default
# applies).

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
ENV_TEMPLATE
    echo -e "${YELLOW}No .env found — created one with default/placeholder values.${NC}"
    echo -e "${YELLOW} Fill in real API keys/secrets in .env before things go fully live.${NC}"
fi

# .env holds API keys/secrets — make sure only the owner can read it
if [ -f ".env" ]; then
    chmod 600 ".env"
fi

# Install/upgrade dependencies quietly
echo -e "${CYAN}Checking dependencies...${NC}"
pip install -q -r requirements.txt 2>/dev/null || true

echo ""
echo -e "${CYAN}"
echo " "
echo " "
echo " # # "
echo " ## ### # "
echo " ## # ## # ### "
echo " ## # ### ## ## ## "
echo " # # ### ## ### ## "
echo " ##### ## #### #### # "
echo " ## ## # ## ####### ## ###### "
echo " ## ## ## ####### ############### ## "
echo " # ###### #### ## "
echo " ## ## ## ## "
echo " ##### ## ## "
echo " ## #### "
echo " ### ########## ## ####### ### "
echo " ## ########################################### ### "
echo " ## ######## # ################# # ######## ### "
echo " ### ### #### # ######### ###### ####### ###### "
echo " ###### ## # ######### #### # ######## #### "
echo " ## ###### ## #### ######### ### # ######## ## ### "
echo " ### ## ########### ########### ## ####### "
echo " ###### ## # ### "
echo " # ## ## ## ## ####### "
echo " ##### ###### ### # "
echo " ## ## ## ## "
echo " #### ### ### # "
echo " ### #### ### ## "
echo " ##### ###### ##### # "
echo " ## ##### ##### ## ###### # "
echo " ## ############## # "
echo " ## ####### ## # ### # "
echo " #### ## ## #### # "
echo " ## ## ## ### "
echo " ## # "
echo " ## "
echo " # "
echo " "
echo -e "${GREEN} PROJECT SUNNY — Launching${NC}"
echo -e "${CYAN}"
echo ""

# Route to command
case "$COMMAND" in
    "server")
        echo -e "${GREEN}Starting web server on 0.0.0.0:5000${NC}"
        echo -e "${GREEN}Local: http://127.0.0.1:5000${NC}"
        echo -e "${GREEN}Network/Tailscale: http://100.117.41.53:5000${NC}"
        echo -e "${GREEN}Console: http://100.117.41.53:5000/console${NC}"
        echo -e "${CYAN}Press Ctrl+C to stop${NC}"
        echo ""
        # Direct invocation (not `uvicorn sunny_code.main:app`) so
        # SunnyCore.run() actually runs — that's what starts the Discord bot
        # and, when TLS_CERTFILE/TLS_KEYFILE are set, a second HTTPS server.
        # The bare uvicorn CLI form can only bind one port and never calls
        # run() at all. See main.py's start()/lifespan comments.
        python -m sunny_code.main
        ;;

    "chatbot")
        echo -e "${GREEN}Starting console on 0.0.0.0:5000${NC}"
        echo -e "${GREEN}Local: http://127.0.0.1:5000/console${NC}"
        echo -e "${GREEN}Network/Tailscale: http://100.117.41.53:5000/console${NC}"
        echo -e "${CYAN}Press Ctrl+C to stop${NC}"
        echo ""
        python -m sunny_code.main
        ;;

    "reload")
        echo -e "${GREEN}Starting web server on 0.0.0.0:5000 (auto-reload — local dev only)${NC}"
        echo -e "${GREEN}Local: http://127.0.0.1:5000${NC}"
        echo -e "${CYAN}Press Ctrl+C to stop${NC}"
        echo ""
        python -m uvicorn sunny_code.main:app --reload --host 0.0.0.0 --port 5000
        ;;

    "chat")
        python chat.py
        ;;

    "cli")
        case "$SUBCOMMAND" in
            "briefing")
                echo -e "${GREEN}Starting Briefing CLI${NC}"
                python test_briefing_interactive.py
                ;;
            "tasks")
                echo -e "${GREEN}Starting Task Management CLI${NC}"
                python test_tasks_interactive.py
                ;;
            *)
                echo -e "${YELLOW}Usage: ./run.sh cli [briefing|tasks]${NC}"
                ;;
        esac
        ;;

    "test")
        case "$SUBCOMMAND" in
            "briefing")
                echo -e "${GREEN}Running Briefing Tests${NC}"
                python test_briefing_complete.py
                ;;
            "tasks")
                echo -e "${GREEN}Running Task System Tests${NC}"
                python test_tasks_complete.py
                ;;
            "all")
                echo -e "${GREEN}Running All Tests${NC}"
                python test_briefing_complete.py
                python test_tasks_complete.py
                ;;
            *)
                echo -e "${YELLOW}Usage: ./run.sh test [briefing|tasks|all]${NC}"
                ;;
        esac
        ;;

    "dev")
        echo -e "${GREEN}Development Mode (venv activated)${NC}"
        echo -e "${CYAN}You can now run Python commands directly${NC}"
        echo -e "${CYAN}Exit: exit${NC}"
        echo ""
        bash
        ;;

    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        echo -e "${YELLOW}Available commands:${NC}"
        echo -e " ${CYAN}./run.sh${NC} Start web server (default) — this is what systemd runs"
        echo -e " ${CYAN}./run.sh reload${NC} Same, with auto-reload on file changes — local dev only"
        echo -e " ${CYAN}./run.sh chat${NC} Terminal chat — full assistant, no web server needed"
        echo -e " ${CYAN}./run.sh cli briefing${NC} Start briefing CLI"
        echo -e " ${CYAN}./run.sh cli tasks${NC} Start task management CLI"
        echo -e " ${CYAN}./run.sh test briefing${NC} Test briefing system"
        echo -e " ${CYAN}./run.sh test tasks${NC} Test task system"
        echo -e " ${CYAN}./run.sh test all${NC} Run all tests"
        echo -e " ${CYAN}./run.sh dev${NC} Open dev shell with venv active"
        ;;
esac
