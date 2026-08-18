# Project SUNNY — Auto-launch with venv
# Usage: .\run.ps1 [command] [args...]
# Examples:
#   .\run.ps1                           # Start web server (default)
#   .\run.ps1 chatbot                   # Start chatbot
#   .\run.ps1 cli briefing              # Start briefing CLI
#   .\run.ps1 cli tasks                 # Start tasks CLI
#   .\run.ps1 test briefing             # Run briefing tests
#   .\run.ps1 test tasks                # Run tasks tests

param(
    [string]$Command = "server",
    [string]$Subcommand = "",
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

# Check if venv exists
if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "⚠️  Virtual environment not found. Creating..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
}

# Activate venv
& ".\venv\Scripts\Activate.ps1"

# Install/upgrade dependencies silently
Write-Host "Checking dependencies..." -ForegroundColor Gray
pip install -q -r requirements.txt 2>$null

Write-Host ""
Write-Host "╔════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   🌞 PROJECT SUNNY — Launching         ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Route to command
switch ($Command.ToLower()) {
    "server" {
        Write-Host "Starting web server on http://127.0.0.1:5000" -ForegroundColor Green
        Write-Host "Chatbot UI: http://127.0.0.1:5000/chatbot" -ForegroundColor Green
        Write-Host "API Docs: http://127.0.0.1:5000/docs" -ForegroundColor Green
        Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
        Write-Host ""
        python -m uvicorn sunny.main:app --reload --host 127.0.0.1 --port 5000
    }

    "chatbot" {
        Write-Host "Starting chatbot on http://127.0.0.1:5000/chatbot" -ForegroundColor Green
        Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
        Write-Host ""
        python -m uvicorn sunny.main:app --host 127.0.0.1 --port 5000
    }

    "cli" {
        switch ($Subcommand.ToLower()) {
            "briefing" {
                Write-Host "Starting Briefing CLI" -ForegroundColor Green
                python test_briefing_interactive.py
            }
            "tasks" {
                Write-Host "Starting Task Management CLI" -ForegroundColor Green
                python test_tasks_interactive.py
            }
            default {
                Write-Host "Usage: .\run.ps1 cli [briefing|tasks]" -ForegroundColor Yellow
            }
        }
    }

    "test" {
        switch ($Subcommand.ToLower()) {
            "briefing" {
                Write-Host "Running Briefing Tests" -ForegroundColor Green
                python test_briefing_complete.py
            }
            "tasks" {
                Write-Host "Running Task System Tests" -ForegroundColor Green
                python test_tasks_complete.py
            }
            "all" {
                Write-Host "Running All Tests" -ForegroundColor Green
                python test_briefing_complete.py
                python test_tasks_complete.py
            }
            default {
                Write-Host "Usage: .\run.ps1 test [briefing|tasks|all]" -ForegroundColor Yellow
            }
        }
    }

    "dev" {
        Write-Host "Development Mode (venv activated)" -ForegroundColor Green
        Write-Host "You can now run Python commands directly" -ForegroundColor Gray
        Write-Host "Exit: exit" -ForegroundColor Gray
        Write-Host ""
        # Keep shell open for manual commands
    }

    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Write-Host "Available commands:" -ForegroundColor Yellow
        Write-Host "  .\run.ps1                    Start web server (default)" -ForegroundColor Gray
        Write-Host "  .\run.ps1 chatbot            Start chatbot UI" -ForegroundColor Gray
        Write-Host "  .\run.ps1 cli briefing       Start briefing CLI" -ForegroundColor Gray
        Write-Host "  .\run.ps1 cli tasks          Start task management CLI" -ForegroundColor Gray
        Write-Host "  .\run.ps1 test briefing      Test briefing system" -ForegroundColor Gray
        Write-Host "  .\run.ps1 test tasks         Test task system" -ForegroundColor Gray
        Write-Host "  .\run.ps1 test all           Run all tests" -ForegroundColor Gray
        Write-Host "  .\run.ps1 dev                Open dev shell with venv active" -ForegroundColor Gray
    }
}
