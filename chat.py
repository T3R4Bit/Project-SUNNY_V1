#!/usr/bin/env python
"""Terminal chat — the same assistant as /console and Discord, no browser needed.

Every message routes through sunny_code.components.assistant.handle_message(),
the one shared entry point the web console and the Discord bot already use —
so behavior here is identical: tasks, lists, alarms/reminders, briefings,
Q&A (weather/calendar/email/etc.), "setup <name>", and "help". No separate
copy of any of that logic lives in this file.

Reads from stdin until EOF, so it also works non-interactively for testing:
    echo -e "help\nshow my tasks" | python chat.py
"""

import asyncio
import sys

from sunny_code.components.assistant import handle_message
from sunny_code.components.briefing import BriefingEngine
from sunny_code.components.lists_db import ListDB
from sunny_code.components.lists_engine import ListEngine
from sunny_code.components.scheduled_db import ScheduledDB
from sunny_code.components.scheduled_engine import ScheduledEngine
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_engine import TaskEngine
from sunny_code.config import get_settings

_BANNER = """
☀️  PROJECT SUNNY — Terminal Chat

Same assistant as /console and Discord — tasks, lists, alarms/reminders,
briefings, and Q&A all work exactly the same here, no browser needed.

Type "help" for the full command list, "exit" or Ctrl+D to quit.
"""


async def main():
    settings = get_settings()
    vault_state_dir = settings.project_root / "sunny-vault" / "state"
    tasks_engine = TaskEngine(TaskDB(vault_state_dir / "tasks"))
    briefing_engine = BriefingEngine()
    list_engine = ListEngine(ListDB(vault_state_dir / "lists"))
    scheduled_engine = ScheduledEngine(ScheduledDB(settings.project_root / "scheduled.db"))

    print(_BANNER)

    session_id = "terminal"
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            print()
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            break

        try:
            response = await handle_message(
                text, tasks_engine, briefing_engine, list_engine, scheduled_engine, session_id=session_id
            )
        except Exception as e:
            response = f"❌ Error: {e}"

        print(f"\nsunny> {response}\n")

    print("Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)
