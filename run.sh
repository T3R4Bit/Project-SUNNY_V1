#!/bin/bash
# Project SUNNY — Auto-launch with venv (Bash version)
# Usage: ./run.sh [command]
# Examples:
# ./run.sh Start web server (default) — this is what systemd runs
# ./run.sh reload Same, but with auto-reload on file changes — local dev only
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
#
# Grouped by what each thing actually is, not by when it was added. If
# you're regenerating this after a fresh clone, also see sunny_code/config.py
# — it's the authoritative field list; this template mirrors it.

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
APP_NAME="Project SUNNY"
APP_ENV=development
DEBUG=true

# ---------------------------------------------------------------------------
# Network — binds to this on the Lenovo in production
# ---------------------------------------------------------------------------
TAILSCALE_IP=100.117.41.53
API_PORT=5000
API_HOST=127.0.0.1

# ---------------------------------------------------------------------------
# TLS (optional) — some providers require HTTPS on the redirect/callback URI
# (Google OAuth won't accept a plain-http non-localhost URI; Spotify requires
# HTTPS except literal 127.0.0.1). Blank means "not configured": Sunny serves
# plain HTTP only on API_PORT. Use a Tailscale-issued cert, not a manually-
# managed one — see sunny-vault/docs/architecture/google-integration.md.
# ---------------------------------------------------------------------------
TLS_CERTFILE=
TLS_KEYFILE=
TLS_PORT=5443

# ---------------------------------------------------------------------------
# Claude (Anthropic) — the one paid API here. Spend caps are enforced
# in-app on top of whatever hard cap you also set at console.anthropic.com.
# ---------------------------------------------------------------------------
CLAUDE_API_KEY=sk-ant-...
DAILY_SPEND_CAP=20.0
MONTHLY_SPEND_CAP=100.0
# Freeform-conversation tuning — for genuinely open-ended questions nothing
# else can answer (see briefing.py's custom_briefing()). The actual
# behavior/tone/persona knob is the system prompt itself:
# sunny-vault/docs/instructions/general-chat.md, hand-editable, no restart
# needed. These three are optional and take effect on the very next call.
LLM_CHAT_MODEL=haiku
# haiku (fast/cheap), sonnet (more capable, slower/pricier), opus (rarely
# worth it here) — see llm_client.py's MODELS dict.
LLM_CHAT_MAX_TOKENS=300
# Hard cap on reply length — kept short since these are meant to be brief
# and are often spoken aloud.
LLM_CHAT_TEMPERATURE=
# 0.0 = deterministic, 1.0 = Anthropic's own default, higher = more
# varied/less literal. Blank leaves it unset (the API's own default applies).

# ---------------------------------------------------------------------------
# Weather (OpenWeatherMap)
# ---------------------------------------------------------------------------
OPENWEATHERMAP_API_KEY=...
# Optional fallback only — set your real location via POST
# /api/weather/location instead, it saves instantly with no restart. See
# sunny-vault/docs/architecture/location.md. Format if you do set it here:
# "City,State,CountryCode" — e.g. Detroit,MI,US (state code only applies to US)
WEATHER_LOCATION=...

# ---------------------------------------------------------------------------
# Location (OwnTracks phone GPS — see "setup gps")
# ---------------------------------------------------------------------------
# Blank means the /api/location/owntracks endpoint accepts reports with no
# auth at all (fine for personal use over Tailscale).
OWNTRACKS_SHARED_SECRET=

# ---------------------------------------------------------------------------
# Google Sign-In (OAuth 2.0) — powers Calendar (read + create/delete) and
# Gmail (read-only). Setup: sunny-vault/docs/architecture/google-integration.md
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://100.117.41.53:5000/auth/google/callback

# ---------------------------------------------------------------------------
# Spotify (OAuth 2.0, PKCE) — powers voice playback control. Requires
# Premium. Setup: sunny-vault/docs/architecture/spotify-integration.md
# ---------------------------------------------------------------------------
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_OAUTH_REDIRECT_URI=https://sunshine-m700.wahoo-sidewinder.ts.net:5443/auth/spotify/callback

# ---------------------------------------------------------------------------
# Discord bot — leave token/chat-channel blank to run without the bot
# (terminal chat via ./run.sh chat still works). See sunny-vault/docs/architecture/discord-bot.md
# ---------------------------------------------------------------------------
DISCORD_BOT_TOKEN=
# Required — the one channel commands are read from.
DISCORD_CHAT_CHANNEL_ID=
# Optional — a separate, read-only home for the pinned task dashboard so it
# doesn't get buried in a busy chat channel. Falls back to the chat channel
# above if left blank (nothing breaks either way).
DISCORD_TASKS_CHANNEL_ID=
# Optional output-only channels — leave blank to keep everything posting to
# the chat channel above instead (nothing breaks either way).
DISCORD_BRIEFINGS_CHANNEL_ID=
DISCORD_WARNINGS_CHANNEL_ID=
DISCORD_TASK_UPDATES_CHANNEL_ID=
DISCORD_HEALTH_CHANNEL_ID=
# Claude API usage dashboard + spend-cap alerts — falls back to the health
# channel above, then chat, if left blank. Give it its own channel if you
# don't want usage posts mixed in with the weekly health report.
DISCORD_USAGE_CHANNEL_ID=
# Class-deadline reminders (class_deadlines.py's T-2/T-0 pings) — same
# falls-back-to-chat behavior as the output channels above.
DISCORD_REMINDERS_CHANNEL_ID=
# The voice channel Sunny stays connected to persistently — unlike the
# output-only channels above, unset means voice presence just doesn't
# start, not "falls back to chat." Say "Hey Sunny" before each request
# once connected; toggle on/off later with /service voice_join.
DISCORD_VOICE_CHANNEL_ID=

# ---------------------------------------------------------------------------
# Voice — Piper (TTS, /speak + live voice presence) and Vosk (STT, live
# voice presence only). Both free, fully local, no API key. Models download
# automatically on first use. See sunny-vault/docs/architecture/tts-piper.md
# and voice-join.md.
# ---------------------------------------------------------------------------
PIPER_VOICE=en_US-lessac-medium
# Optional tuning — leave blank for the voice's own defaults. See
# tts-piper.md's "Tuning Piper's Voice" for what each does and where to start.
PIPER_LENGTH_SCALE=
PIPER_NOISE_SCALE=
PIPER_NOISE_W_SCALE=
PIPER_SPEAKER_ID=
VOSK_LANG=en-us
# Specific model by name, bigger vocabulary than VOSK_LANG's small default.
# Leave blank (small model) — vosk-model-en-us-0.22-lgraph crashes voice
# outright (a real Kaldi assertion failure inside its own incremental
# lattice decoder, not fixable from this app — see config.py and
# sunny-vault/docs/architecture/voice-join.md). If accuracy ever needs
# revisiting, try vosk-model-en-us-0.22 (the non-"-lgraph" big model,
# ~1.8GB) instead, not the lgraph one.
VOSK_MODEL_NAME=

# ---------------------------------------------------------------------------
# Weekly system health check (Sunday 4am — see
# sunny-vault/docs/architecture/health-check.md)
# ---------------------------------------------------------------------------
# Needs a real IANA name (not "EST"/"PST" abbreviations).
LOCAL_TIMEZONE=America/New_York
# Optional, hand-maintained key expiry dates (YYYY-MM-DD) — the health check
# warns you a week before any of these. Blank = skip that key's check; none
# of these providers expose real expiration dates via API.
CLAUDE_API_KEY_EXPIRES=
OPENWEATHERMAP_API_KEY_EXPIRES=
DISCORD_BOT_TOKEN_EXPIRES=
GOOGLE_CLIENT_SECRET_EXPIRES=

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
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
        echo -e "${CYAN}Press Ctrl+C to stop${NC}"
        echo ""
        # Direct invocation (not `uvicorn sunny_code.main:app`) so
        # SunnyCore.run() actually runs — that's what starts the Discord bot
        # and, when TLS_CERTFILE/TLS_KEYFILE are set, a second HTTPS server.
        # The bare uvicorn CLI form can only bind one port and never calls
        # run() at all. See main.py's start()/lifespan comments.
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
