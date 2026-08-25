#!/usr/bin/env python
"""Interactive task management CLI — test task commands."""

import asyncio
import sys
from pathlib import Path

from sunny_code.config import get_settings
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_engine import TaskEngine


async def main():
    """Interactive task CLI."""
    settings = get_settings()
    db = TaskDB(settings.project_root / "sunny-vault" / "state" / "tasks")
    engine = TaskEngine(db)

    print("""
╔════════════════════════════════════════════════════════════════╗
║ PROJECT SUNNY — TASK MANAGEMENT CLI ║
╚════════════════════════════════════════════════════════════════╝

Test the task system by typing natural commands — no prefix needed.

Commands:
  add Title to my tasks --tag School --due 2026-08-20
  mark abc123 as done
  !task abc123 tag School (field edits still use this terser form)
  delete abc123
  show my tasks
  list tasks --tag School
  list tasks --status done
  list tasks --due-soon

Examples:
  add finish physics homework to my tasks --tag School --due 2026-08-20
  add engine rebuild to my tasks --tag Motorsports
  remind me to learn Rust
  list tasks --open
  list tasks --tag School

The legacy !task/!tasks syntax still works too, if you prefer it.

Type 'help' for all commands, 'exit' to quit.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                print("\nGoodbye!\n")
                sys.exit(0)

            if user_input.lower() == "help":
                print("""
TASK COMMANDS:

Create:
  add Title to my tasks --tag TAG --due DATE
  add task Title / create task Title / new task Title / remind me to Title

  Tags: School, Motorsports, General, Project Ideas (or whatever your live
  category list has — see /category in Discord)
  Date: YYYY-MM-DD

Update:
  mark ID as done / complete ID / finish ID
  !task ID tag TAG (field edits still use this terser form — need the ID)
  !task ID title "New title"
  !task ID describe "Description"
  !task ID due YYYY-MM-DD

Delete:
  delete ID / remove ID

List:
  show my tasks / my tasks / tasks (show open)
  list tasks --status open|done|in_progress
  list tasks --tag TAG
  list tasks --due-soon (due within 7 days)
  list tasks --all (show all)

Examples:
  add exam prep to my tasks --tag School --due 2026-08-25
  !task 3a2b1c status in_progress
  !task 3a2b1c tag Motorsports

The legacy !task/!tasks syntax (shown above for field edits) still works everywhere too.
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
            print("\n\nGoodbye!\n")
            sys.exit(0)
        except Exception as e:
            print(f"\nError: {e}\n")
            continue


if __name__ == "__main__":
    asyncio.run(main())
