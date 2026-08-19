#!/bin/bash
# Project SUNNY — Auto-launch with venv (Bash version)
# Usage: ./run.sh [command]
# Examples:
#   ./run.sh                    Start web server (default)
#   ./run.sh chatbot            Start console (non-reload mode)
#   ./run.sh cli briefing       Start briefing CLI
#   ./run.sh cli tasks          Start tasks CLI
#   ./run.sh test briefing      Run briefing tests
#   ./run.sh test tasks         Run task tests

set -e

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
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
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

# Google Sign-In (OAuth 2.0) — powers Calendar + Gmail (read-only).
# Setup steps: sunny-vault/docs/architecture/google-integration.md
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://100.117.41.53:5000/auth/google/callback

# Discord bot (tasks channel) — leave both blank to run without the bot (console chat still works)
# See sunny-vault/docs/architecture/discord-bot.md for setup steps
DISCORD_BOT_TOKEN=
DISCORD_TASKS_CHANNEL_ID=

# Network (will bind to this on Lenovo in production)
TAILSCALE_IP=100.117.41.53
API_PORT=5000
API_HOST=127.0.0.1

# Spending caps
DAILY_SPEND_CAP=20.0
MONTHLY_SPEND_CAP=100.0

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
ENV_TEMPLATE
    echo -e "${YELLOW}⚠️  No .env found — created one with default/placeholder values.${NC}"
    echo -e "${YELLOW}   Fill in real API keys/secrets in .env before things go fully live.${NC}"
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
echo "                                                                                                    "
echo "                                                                                                    "
echo "                                       #          #                                                 "
echo "                                       ##        ###       #                                        "
echo "                                      ## #      ## #      ###                                       "
echo "                                     ##  #    ### ##     ## ##                                      "
echo "                                     #   #  ###   ##   ###  ##                                      "
echo "                         #####      ##   ####      ####      #                                      "
echo "                           ## ##    #      ##  #######      ##        ######                        "
echo "                            ##  ##  ##  #######      ###############    ##                          "
echo "                             #    ######                   ####       ##                            "
echo "                             ##    ##                          ##    ##                             "
echo "                              #####                              ## ##                              "
echo "                               ##                                 ####                              "
echo "              ###     ##########                                    ##   ####### ###                "
echo "                   ##        ###########################################      ###                   "
echo "                     ##     ########   #  #################  #  ########   ###                      "
echo "                      ###  ### ####  #  #########  ######     ####### ######                        "
echo "                        ######  ##  #  #########    ####  #  ######## ####                          "
echo "              ##  ######    ##  ####  #########      ### #  ########  ##  ###                       "
echo "                ###         ##    ###########          ###########    ##     #######                "
echo "                   ######   ##                                        #            ###              "
echo "                          #  ##             ##         ##            ##    #######                  "
echo "                           #####               ######               ###  #                          "
echo "                          ##   ##                                  ## ##                            "
echo "                       ####     ###                              ###   #                            "
echo "                     ###         ####                          ###     ##                           "
echo "                            ##### ######                    #####       #                           "
echo "                                 ##     #####          #####   ## ###### #                          "
echo "                                ##        ##############       #                                    "
echo "                               ##  #######   ##      # ###     #                                    "
echo "                               ####          ##     ##   ####  #                                    "
echo "                               ##             ##   ##        ###                                    "
echo "                                               ## #                                                 "
echo "                                                ##                                                  "
echo "                                                 #                                                  "
echo "                                                                                                    "
echo -e "${GREEN}                          PROJECT SUNNY — Launching${NC}"
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
        python -m uvicorn sunny_code.main:app --reload --host 0.0.0.0 --port 5000
        ;;

    "chatbot")
        echo -e "${GREEN}Starting console on 0.0.0.0:5000${NC}"
        echo -e "${GREEN}Local: http://127.0.0.1:5000/console${NC}"
        echo -e "${GREEN}Network/Tailscale: http://100.117.41.53:5000/console${NC}"
        echo -e "${CYAN}Press Ctrl+C to stop${NC}"
        echo ""
        python -m uvicorn sunny_code.main:app --host 0.0.0.0 --port 5000
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
        echo -e "  ${CYAN}./run.sh${NC}                Start web server (default)"
        echo -e "  ${CYAN}./run.sh chatbot${NC}         Start console (non-reload mode)"
        echo -e "  ${CYAN}./run.sh cli briefing${NC}    Start briefing CLI"
        echo -e "  ${CYAN}./run.sh cli tasks${NC}       Start task management CLI"
        echo -e "  ${CYAN}./run.sh test briefing${NC}   Test briefing system"
        echo -e "  ${CYAN}./run.sh test tasks${NC}      Test task system"
        echo -e "  ${CYAN}./run.sh test all${NC}        Run all tests"
        echo -e "  ${CYAN}./run.sh dev${NC}             Open dev shell with venv active"
        ;;
esac
