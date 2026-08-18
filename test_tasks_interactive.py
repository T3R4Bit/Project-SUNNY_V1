#!/usr/bin/env python
"""Interactive task management CLI — test task commands."""

import asyncio
import sys
from pathlib import Path

from sunny.config import get_settings
from sunny.components.tasks_db import TaskDB
from sunny.components.tasks_engine import TaskEngine


async def main():
    """Interactive task CLI."""
    settings = get_settings()
    db = TaskDB(settings.project_root / "tasks.db")
    engine = TaskEngine(db)

    print("""
╔════════════════════════════════════════════════════════════════╗
║        📋 PROJECT SUNNY — TASK MANAGEMENT CLI 📋               ║
╚════════════════════════════════════════════════════════════════╝

Test the task system by typing Discord-style commands.

Commands:
  !task add "Title" --tag School --priority 4 --due 2026-08-20
  !task abc123 status done
  !task abc123 priority 5
  !task abc123 delete
  !tasks
  !tasks --tag School
  !tasks --status done
  !tasks --due-soon

Examples:
  !task add "Finish physics homework" --tag School --priority 5 --due 2026-08-20
  !task add "Engine rebuild" --tag Motorsports --priority 4
  !task add "Learn Rust" --tag General --priority 3
  !tasks --open
  !tasks --tag School

Type 'help' for all commands, 'exit' to quit.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                print("\n✨ Goodbye!\n")
                sys.exit(0)

            if user_input.lower() == "help":
                print("""
TASK COMMANDS:

Create:
  !task add "Title" --tag TAG --priority PRIORITY --due DATE

  Tags: School, Motorsports, General, Project Ideas
  Priority: 1-5 (1=low, 5=critical)
  Date: YYYY-MM-DD

Update:
  !task ID status open|in_progress|done
  !task ID priority 1-5
  !task ID tag TAG
  !task ID title "New title"
  !task ID describe "Description"
  !task ID due YYYY-MM-DD

Delete:
  !task ID delete

List:
  !tasks                      (show open)
  !tasks --status open|done|in_progress
  !tasks --tag TAG
  !tasks --priority 4         (priority 4+)
  !tasks --due-soon           (due within 7 days)
  !tasks --all                (show all)

Examples:
  !task add "Exam prep" --tag School --priority 5 --due 2026-08-25
  !task 3a2b1c status in_progress
  !task 3a2b1c priority 5
                """)
                continue

            if user_input.lower() == "dashboard":
                dashboard = engine.format_dashboard()
                print("\n" + "=" * 70)
                print(dashboard)
                print("=" * 70 + "\n")
                continue

            # Execute command
            print()
            success, message = await engine.execute_command(user_input)
            print(message)
            print()

        except KeyboardInterrupt:
            print("\n\n✨ Goodbye!\n")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            continue


if __name__ == "__main__":
    asyncio.run(main())
