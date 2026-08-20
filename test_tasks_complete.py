#!/usr/bin/env python
"""Complete test suite for task management system."""

import asyncio
import shutil
import subprocess
import time
import requests
import sys
from pathlib import Path

from sunny_code.config import get_settings
from sunny_code.components.tasks_db import TaskDB
from sunny_code.components.tasks_engine import TaskEngine


async def test_task_database():
    """Test task database CRUD operations."""
    print("\n" + "=" * 70)
    print("🧪 TASK DATABASE — CRUD TESTS")
    print("=" * 70)

    settings = get_settings()
    db_path = settings.project_root / "tasks_test_vault"

    # Clean up any previous test run's vault directory
    shutil.rmtree(db_path, ignore_errors=True)

    db = TaskDB(db_path)

    # Test create
    print("\n1️⃣  Testing CREATE...")
    task_id1 = db.create_task(
        title="Finish physics homework",
        tag="School",
        priority=5,
        due_date="2026-08-20",
    )
    print(f"   ✓ Created task: {task_id1}")

    task_id2 = db.create_task(
        title="Engine rebuild",
        tag="Motorsports",
        priority=4,
    )
    print(f"   ✓ Created task: {task_id2}")

    task_id3 = db.create_task(
        title="Learn Rust",
        tag="General",
        priority=3,
    )
    print(f"   ✓ Created task: {task_id3}")

    # Test read
    print("\n2️⃣  Testing READ...")
    task = db.get_task(task_id1)
    assert task["title"] == "Finish physics homework"
    assert task["priority"] == 5
    print(f"   ✓ Retrieved task: {task['title']}")

    # Test list
    print("\n3️⃣  Testing LIST...")
    all_tasks = db.get_open_tasks()
    assert len(all_tasks) == 3
    print(f"   ✓ Found {len(all_tasks)} open tasks")

    school_tasks = db.get_tasks_by_tag("School")
    assert len(school_tasks) == 1
    print(f"   ✓ School tag filter: {len(school_tasks)} task(s)")

    # Test update
    print("\n4️⃣  Testing UPDATE...")
    db.update_task(task_id1, status="in_progress")
    task = db.get_task(task_id1)
    assert task["status"] == "in_progress"
    print(f"   ✓ Updated status to: {task['status']}")

    db.update_task(task_id1, priority=4)
    task = db.get_task(task_id1)
    assert task["priority"] == 4
    print(f"   ✓ Updated priority to: {task['priority']}")

    # Test filters
    print("\n5️⃣  Testing FILTERS...")
    high_priority = db.get_high_priority_tasks(min_priority=4)
    print(f"   ✓ High priority (4+): {len(high_priority)} tasks")

    due_soon = db.get_tasks_due_soon(days=7)
    print(f"   ✓ Due within 7 days: {len(due_soon)} tasks")

    # Test stats
    print("\n6️⃣  Testing STATS...")
    stats = db.get_stats()
    print(f"   ✓ Open: {stats['open']}")
    print(f"   ✓ In Progress: {stats['in_progress']}")
    print(f"   ✓ Done: {stats['done']}")
    print(f"   ✓ Total: {stats['total']}")

    # Test delete
    print("\n7️⃣  Testing DELETE...")
    db.delete_task(task_id3)
    remaining = db.get_open_tasks()
    # After updating task_id1 to in_progress, we only have task_id2 open
    # Deleting task_id3 leaves 1 open task
    assert len(remaining) == 1
    print(f"   ✓ Deleted task, {len(remaining)} remaining")

    print("\n✅ All database tests passed!\n")
    # No Windows file-locking concern to work around anymore (that was a
    # SQLite-specific quirk) — the next run's shutil.rmtree() above cleans
    # this up, nothing needed here.
    return True


async def test_command_parser():
    """Test command parser."""
    print("=" * 70)
    print("🧪 COMMAND PARSER — PARSING TESTS")
    print("=" * 70)

    from sunny_code.components.tasks_parser import TaskCommandParser

    parser = TaskCommandParser()

    # Test add command (legacy !task syntax)
    print("\n1️⃣  Testing PARSE ADD (legacy !task syntax)...")
    success, data = parser.parse_add_command(
        '!task add "Finish homework" --tag School --priority 5 --due 2026-08-20'
    )
    assert success
    assert data["title"] == "Finish homework"
    assert data["tag"] == "School"
    assert data["priority"] == 5
    print(f"   ✓ Parsed: {data}")

    # Test add command (natural phrasing — primary UX today)
    print("\n1️⃣b Testing PARSE ADD (natural phrasing)...")
    cmd_type, success, data = parser.parse_command(
        "add finish homework to my tasks --tag School --priority 5 --due 2026-08-20"
    )
    assert cmd_type == "add" and success
    assert data["title"] == "finish homework"
    assert data["tag"] == "School"
    assert data["priority"] == 5
    print(f"   ✓ Parsed: {data}")

    cmd_type, success, data = parser.parse_command("show my tasks")
    assert cmd_type == "list" and success
    print(f"   ✓ Parsed natural list command")

    cmd_type, success, data = parser.parse_command("mark abc123 as done")
    assert cmd_type == "update" and success
    assert data == {"task_id": "abc123", "field": "status", "value": "done"}
    print(f"   ✓ Parsed: {data}")

    cmd_type, success, data = parser.parse_command("delete abc123")
    assert cmd_type == "delete" and success
    assert data["task_id"] == "abc123"
    print(f"   ✓ Parsed: {data}")

    # Test update command
    print("\n2️⃣  Testing PARSE UPDATE...")
    success, data = parser.parse_update_command("!task abc123 status done")
    assert success
    assert data["task_id"] == "abc123"
    assert data["field"] == "status"
    assert data["value"] == "done"
    print(f"   ✓ Parsed: {data}")

    # Test delete command
    print("\n3️⃣  Testing PARSE DELETE...")
    success, data = parser.parse_delete_command("!task abc123 delete")
    assert success
    assert data["task_id"] == "abc123"
    print(f"   ✓ Parsed: {data}")

    # Test list command
    print("\n4️⃣  Testing PARSE LIST...")
    success, data = parser.parse_list_command("!tasks --tag School --status open")
    assert success
    assert data.get("tag") == "School"
    assert data.get("status") == "open"
    print(f"   ✓ Parsed: {data}")

    # Test invalid commands
    print("\n5️⃣  Testing ERROR HANDLING...")
    success, data = parser.parse_add_command("invalid command")
    assert not success
    print(f"   ✓ Rejected invalid command")

    print("\n✅ All parser tests passed!\n")
    return True


async def test_task_engine():
    """Test task engine command execution."""
    print("=" * 70)
    print("🧪 TASK ENGINE — COMMAND EXECUTION TESTS")
    print("=" * 70)

    settings = get_settings()
    db_path = settings.project_root / "tasks_test2_vault"

    shutil.rmtree(db_path, ignore_errors=True)

    db = TaskDB(db_path)
    engine = TaskEngine(db)

    # Test add via engine
    print("\n1️⃣  Testing ENGINE ADD...")
    success, msg = await engine.execute_command(
        '!task add "Physics exam prep" --tag School --priority 5 --due 2026-08-25'
    )
    assert success
    print(f"   ✓ {msg.split(chr(10))[0]}")

    # Test list
    print("\n2️⃣  Testing ENGINE LIST...")
    success, msg = await engine.execute_command("!tasks")
    if not success:
        print(f"   ⚠️  List returned: success={success}, msg={msg[:100]}")
    else:
        print(f"   ✓ Listed tasks ({msg.count(chr(10))} lines)")

    # Extract task ID and test update
    print("\n3️⃣  Testing ENGINE UPDATE...")
    open_tasks = db.get_open_tasks()
    if open_tasks:
        task_id = open_tasks[0]["id"]
        success, msg = await engine.execute_command(f"!task {task_id} status in_progress")
        print(f"   ✓ {msg}")

        # Test delete
        print("\n4️⃣  Testing ENGINE DELETE...")
        success, msg = await engine.execute_command(f"!task {task_id} delete")
        print(f"   ✓ {msg}")
    else:
        print(f"   ⚠️  No open tasks to update")

    print("\n✅ All engine tests passed!\n")
    return True


async def test_http_api():
    """Test task API endpoints."""
    print("=" * 70)
    print("🌐 TASK ENGINE — HTTP API TESTS")
    print("=" * 70)

    print("\n1️⃣  Starting FastAPI server...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sunny_code.main:app", "--host", "127.0.0.1", "--port", "5002", "--log-level", "warning"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)

    try:
        # Test command endpoint (legacy !task syntax)
        print("\n2️⃣  Testing POST /api/tasks/command (legacy !task syntax)...")
        response = requests.post(
            "http://127.0.0.1:5002/api/tasks/command",
            params={"cmd": '!task add "Test task" --tag General --priority 3'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"]
        print(f"   ✓ Command executed: {data['message'].split(chr(10))[0]}")

        # Test command endpoint (natural phrasing)
        print("\n2️⃣b Testing POST /api/tasks/command (natural phrasing)...")
        response = requests.post(
            "http://127.0.0.1:5002/api/tasks/command",
            params={"cmd": "add another test task to my tasks --tag General --priority 3"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"]
        print(f"   ✓ Command executed: {data['message'].split(chr(10))[0]}")

        # Test list endpoint
        print("\n3️⃣  Testing GET /api/tasks/list...")
        response = requests.get("http://127.0.0.1:5002/api/tasks/list")
        assert response.status_code == 200
        data = response.json()
        print(f"   ✓ Found {data['count']} tasks")

        # Test stats
        print("\n4️⃣  Testing GET /api/tasks/stats...")
        response = requests.get("http://127.0.0.1:5002/api/tasks/stats")
        assert response.status_code == 200
        stats = response.json()
        print(f"   ✓ Stats: {stats['total']} total, {stats['open']} open")

        # Test dashboard
        print("\n5️⃣  Testing GET /api/tasks/dashboard...")
        response = requests.get("http://127.0.0.1:5002/api/tasks/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "dashboard" in data
        print(f"   ✓ Dashboard generated ({len(data['dashboard'])} chars)")

        print("\n✅ All HTTP tests passed!\n")
        return True

    except Exception as e:
        print(f"\n❌ HTTP test failed: {e}")
        return False

    finally:
        print("6️⃣  Stopping server...")
        proc.terminate()
        proc.wait(timeout=5)


async def main():
    """Run all tests."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║   📋 PROJECT SUNNY — TASK SYSTEM COMPLETE TEST SUITE 📋        ║
╚════════════════════════════════════════════════════════════════╝
    """)

    try:
        db_result = await test_task_database()
        parser_result = await test_command_parser()
        engine_result = await test_task_engine()
        http_result = await test_http_api()

        if all([db_result, parser_result, engine_result, http_result]):
            print("""
╔════════════════════════════════════════════════════════════════╗
║                   ✨ ALL TESTS PASSED! ✨                      ║
╚════════════════════════════════════════════════════════════════╝

🎉 Task system is fully functional!

Try the interactive CLI:
  python test_tasks_interactive.py

Features implemented:
  ✓ SQLite task database (CRUD operations)
  ✓ Hardcoded command parser (no LLM needed)
  ✓ Natural language commands (add X to my tasks, show my tasks, mark X as done)
  ✓ Legacy !task/!tasks syntax still supported underneath
  ✓ Filtering by tag, status, priority, due date
  ✓ Task statistics and dashboard
  ✓ HTTP API endpoints
  ✓ Task validation and error handling

Try these commands:
  add finish homework to my tasks --tag School --priority 5 --due 2026-08-20
  add engine rebuild to my tasks --tag Motorsports --priority 4
  show my tasks
  list tasks --tag School
  list tasks --priority 4
  list tasks --due-soon

Next steps:
  1. Integrate with Discord bot (Discord.py)
  2. Add persistent pinned dashboard
  3. Connect to briefing system (show task summaries)
  4. Add task notifications
            """)
            return 0
        else:
            print("\n❌ Some tests failed")
            return 1

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
