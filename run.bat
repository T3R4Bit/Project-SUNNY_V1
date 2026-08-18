@echo off
REM Project SUNNY — Auto-launch with venv
REM Usage: run.bat [command]
REM Examples:
REM   run.bat                  Start web server (default)
REM   run.bat chatbot          Start chatbot
REM   run.bat cli-briefing     Start briefing CLI
REM   run.bat cli-tasks        Start tasks CLI
REM   run.bat test-briefing    Run briefing tests

setlocal enabledelayedexpansion

if "%1"=="" (
    set CMD=server
) else (
    set CMD=%1
)

REM Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install dependencies quietly
pip install -q -r requirements.txt 2>nul

echo.
echo ====================================
echo    Project SUNNY - Launching
echo ====================================
echo.

REM Route to command
if "%CMD%"=="server" (
    echo Starting web server on http://127.0.0.1:5000
    echo Chatbot UI: http://127.0.0.1:5000/chatbot
    echo API Docs: http://127.0.0.1:5000/docs
    echo Press Ctrl+C to stop
    echo.
    python -m uvicorn sunny.main:app --reload --host 127.0.0.1 --port 5000
) else if "%CMD%"=="chatbot" (
    echo Starting chatbot on http://127.0.0.1:5000/chatbot
    echo Press Ctrl+C to stop
    echo.
    python -m uvicorn sunny.main:app --host 127.0.0.1 --port 5000
) else if "%CMD%"=="cli-briefing" (
    echo Starting Briefing CLI
    python test_briefing_interactive.py
) else if "%CMD%"=="cli-tasks" (
    echo Starting Task Management CLI
    python test_tasks_interactive.py
) else if "%CMD%"=="test-briefing" (
    echo Running Briefing Tests
    python test_briefing_complete.py
) else if "%CMD%"=="test-tasks" (
    echo Running Task System Tests
    python test_tasks_complete.py
) else if "%CMD%"=="test-all" (
    echo Running All Tests
    python test_briefing_complete.py
    python test_tasks_complete.py
) else if "%CMD%"=="dev" (
    echo Development Mode - venv activated
    echo Run 'exit' to deactivate venv
) else (
    echo Unknown command: %CMD%
    echo.
    echo Available commands:
    echo   run.bat                Start web server (default)
    echo   run.bat chatbot        Start chatbot UI
    echo   run.bat cli-briefing   Start briefing CLI
    echo   run.bat cli-tasks      Start task management CLI
    echo   run.bat test-briefing  Test briefing system
    echo   run.bat test-tasks     Test task system
    echo   run.bat test-all       Run all tests
    echo   run.bat dev            Open dev shell with venv active
)

endlocal
