#!/usr/bin/env python
"""Complete test suite for briefing engine — CLI and HTTP."""

import asyncio
import subprocess
import time
import requests
import sys
from pathlib import Path


async def test_cli_briefings():
    """Test briefing engine through CLI."""
    print("\n" + "=" * 70)
    print("🧪 BRIEFING ENGINE — CLI TESTS")
    print("=" * 70)

    from sunny.components.briefing import BriefingEngine

    engine = BriefingEngine()

    # Test morning briefing
    print("\n1️⃣  Testing morning briefing...")
    morning = await engine.generate_morning_briefing()
    assert "Good morning" in morning
    assert "PROJECT SUNNY" in morning
    assert "WEATHER" in morning
    print(f"   ✓ Morning briefing generated ({len(morning)} chars)")
    print(f"   Preview: {morning[:200]}...")

    # Test evening briefing
    print("\n2️⃣  Testing evening briefing...")
    evening = await engine.generate_evening_briefing()
    assert "Good evening" in evening
    assert "ACCOMPLISHED" in evening
    print(f"   ✓ Evening briefing generated ({len(evening)} chars)")
    print(f"   Preview: {evening[:200]}...")

    # Test Q&A
    print("\n3️⃣  Testing Q&A functionality...")
    test_questions = [
        "What's the weather?",
        "When is my first meeting?",
        "How many emails do I have?",
        "Tell me about my tasks",
        "What's happening tomorrow?",
        "Any motorsports updates?",
    ]

    for question in test_questions:
        response = await engine.answer_question(question)
        assert len(response) > 50
        print(f"   ✓ Q: '{question}'")
        print(f"     Response length: {len(response)} chars")

    print("\n✅ All CLI tests passed!\n")
    return True


async def test_http_briefings():
    """Test briefing engine through HTTP API."""
    print("=" * 70)
    print("🌐 BRIEFING ENGINE — HTTP API TESTS")
    print("=" * 70)

    # Start server
    print("\n1️⃣  Starting FastAPI server...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sunny.main:app", "--host", "127.0.0.1", "--port", "5001", "--log-level", "warning"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)

    try:
        # Test morning endpoint
        print("\n2️⃣  Testing GET /api/briefing/morning...")
        response = requests.get("http://127.0.0.1:5001/api/briefing/morning")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "morning"
        assert "Good morning" in data["content"]
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Content length: {len(data['content'])} chars")

        # Test evening endpoint
        print("\n3️⃣  Testing GET /api/briefing/evening...")
        response = requests.get("http://127.0.0.1:5001/api/briefing/evening")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "evening"
        assert "Good evening" in data["content"]
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Content length: {len(data['content'])} chars")

        # Test Q&A endpoint
        print("\n4️⃣  Testing GET /api/briefing/ask (Q&A)...")
        questions = [
            "What's the weather?",
            "When is my meeting?",
            "How many tasks do I have?",
        ]

        for question in questions:
            response = requests.get(
                "http://127.0.0.1:5001/api/briefing/ask",
                params={"q": question}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["question"] == question
            assert len(data["response"]) > 50
            print(f"   ✓ '{question}' → {len(data['response'])} chars")

        print("\n✅ All HTTP tests passed!\n")
        return True

    except Exception as e:
        print(f"\n❌ HTTP test failed: {e}")
        return False

    finally:
        print("\n5️⃣  Stopping server...")
        proc.terminate()
        proc.wait(timeout=5)
        print("   ✓ Server stopped")


async def main():
    """Run all tests."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║   🌞 PROJECT SUNNY — BRIEFING ENGINE COMPLETE TEST SUITE 🌞    ║
╚════════════════════════════════════════════════════════════════╝
    """)

    try:
        # Run CLI tests
        cli_result = await test_cli_briefings()

        # Run HTTP tests
        http_result = await test_http_briefings()

        if cli_result and http_result:
            print("""
╔════════════════════════════════════════════════════════════════╗
║                   ✨ ALL TESTS PASSED! ✨                      ║
╚════════════════════════════════════════════════════════════════╝

🎉 Briefing engine is fully functional!

Try the interactive CLI:
  python test_briefing_interactive.py

Features implemented:
  ✓ Morning briefing (9 sections)
  ✓ Evening briefing (7 sections)
  ✓ Q&A engine (weather, calendar, email, tasks, etc.)
  ✓ Mock data (realistic-looking test data)
  ✓ HTTP API endpoints
  ✓ Interactive CLI

Next steps:
  1. Integrate real APIs (Calendar, Weather, Email)
  2. Add scheduling (7am morning, 9pm evening)
  3. Add persistent storage (Obsidian vault logging)
  4. Deploy to Lenovo brain via git push
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
