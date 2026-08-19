#!/bin/bash
# Project SUNNY — Auto-launch with venv (Bash version)
# Usage: ./run.sh [command]
# Examples:
#   ./run.sh                    Start web server (default)
#   ./run.sh chatbot            Start chatbot
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
        echo -e "${GREEN}Chatbot UI: http://100.117.41.53:5000/chatbot${NC}"
        echo -e "${CYAN}Press Ctrl+C to stop${NC}"
        echo ""
        python -m uvicorn sunny.main:app --reload --host 0.0.0.0 --port 5000
        ;;

    "chatbot")
        echo -e "${GREEN}Starting chatbot on 0.0.0.0:5000${NC}"
        echo -e "${GREEN}Local: http://127.0.0.1:5000/chatbot${NC}"
        echo -e "${GREEN}Network/Tailscale: http://100.117.41.53:5000/chatbot${NC}"
        echo -e "${CYAN}Press Ctrl+C to stop${NC}"
        echo ""
        python -m uvicorn sunny.main:app --host 0.0.0.0 --port 5000
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
        echo -e "  ${CYAN}./run.sh chatbot${NC}         Start chatbot UI"
        echo -e "  ${CYAN}./run.sh cli briefing${NC}    Start briefing CLI"
        echo -e "  ${CYAN}./run.sh cli tasks${NC}       Start task management CLI"
        echo -e "  ${CYAN}./run.sh test briefing${NC}   Test briefing system"
        echo -e "  ${CYAN}./run.sh test tasks${NC}      Test task system"
        echo -e "  ${CYAN}./run.sh test all${NC}        Run all tests"
        echo -e "  ${CYAN}./run.sh dev${NC}             Open dev shell with venv active"
        ;;
esac
