#!/usr/bin/env python
"""Interactive briefing test tool — ask questions about your day."""

import asyncio
import sys
from sunny_code.components.briefing import BriefingEngine


async def main():
    """Interactive Q&A interface."""
    engine = BriefingEngine()

    print("""
╔════════════════════════════════════════════════════════════════╗
║        🌞 PROJECT SUNNY — BRIEFING TEST INTERFACE 🌞           ║
╚════════════════════════════════════════════════════════════════╝

Test the briefing engine by asking questions or requesting full briefings.

Commands:
  morning         — Generate full morning briefing
  evening         — Generate full evening briefing
  [question]      — Ask a specific question
  help            — Show available topics
  exit/quit       — Exit the program

Examples:
  • "What's the weather?"
  • "When is my first meeting?"
  • "How many emails do I have?"
  • "Tell me about tomorrow"
  • "What's my mood today?"

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
Available briefing topics:
  🌤️  Weather      → "What's the weather?" or "Will it rain?"
  📅 Calendar     → "What's my schedule?" or "When is my meeting?"
  📧 Email        → "How many emails?" or "What's urgent?"
  ✅ Tasks        → "What are my tasks?" or "What should I do?"
  🚗 Commute      → "What's the traffic?" or "How long to campus?"
  ❤️  Wellness    → "How's my health?" or "How did I sleep?"
  🏁 Motorsports  → "Any racing news?" or "F1 updates?"
  📰 News         → "What's happening?" or "Any headlines?"
  📅 Tomorrow     → "What's tomorrow?" or "Tomorrow's forecast?"
                """)
                continue

            if user_input.lower() == "morning":
                print("\n" + "=" * 70)
                response = await engine.generate_morning_briefing()
                print(response)
                print("=" * 70 + "\n")
                continue

            if user_input.lower() == "evening":
                print("\n" + "=" * 70)
                response = await engine.generate_evening_briefing()
                print(response)
                print("=" * 70 + "\n")
                continue

            # Custom question
            print("\n" + "─" * 70)
            response = await engine.answer_question(user_input)
            print(response)
            print("─" * 70 + "\n")

        except KeyboardInterrupt:
            print("\n\n✨ Goodbye!\n")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            continue


if __name__ == "__main__":
    asyncio.run(main())
