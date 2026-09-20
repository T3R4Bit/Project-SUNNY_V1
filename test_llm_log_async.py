#!/usr/bin/env python
"""Regression test for plan item B5: log_llm_call()'s file I/O used to run
inline on the event loop from every call site in ask_claude()/
ask_claude_stream() (unlike _call_claude_sync, already wrapped in
asyncio.to_thread). Proves (1) the log entry still gets written with the
same content, and (2) it now runs off the event loop (a concurrent
coroutine keeps making progress while it writes). Plain assert-based
script, matching the style of test_routing_fixes.py.

Exercises the cheap "not_configured" refusal path (no real Claude API key
needed) through _preflight_refusal -> log_llm_call_async, which is the
exact path this fix touches (_preflight_refusal became async).
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


async def main():
    tmp = Path(tempfile.mkdtemp())
    os.environ["PROJECT_ROOT"] = str(tmp)
    os.environ["CLAUDE_API_KEY"] = ""  # not looks_configured() -> refusal path

    import sunny_code.config as config_module
    config_module._settings_cache = None

    from sunny_code.components import llm_client

    # --- Part 1: content correctness through the new async path ---
    result = await llm_client.ask_claude("what's the weather", purpose="general-chat")
    check("ask_claude returns None on the not_configured refusal path", result is None)

    log_path = tmp / "sunny-vault" / "log" / "llm-usage.md"
    check("log_llm_call_async actually wrote the log file", log_path.exists())
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        check("log entry has the expected purpose/status", "general-chat" in content and "not_configured" in content)
        check("log entry includes the prompt", "what's the weather" in content)

    # --- Part 2: it actually runs off the event loop now ---
    tick_count = 0
    stop = False

    async def ticker():
        nonlocal tick_count, stop
        while not stop:
            tick_count += 1
            await asyncio.sleep(0.001)

    # Make log_llm_call artificially slow (simulating a busy disk) so a
    # blocking-on-loop regression would be obvious: if log_llm_call_async
    # ran inline, the ticker would be unable to advance while this sleeps.
    real_log_llm_call = llm_client.log_llm_call

    def slow_log_llm_call(*args, **kwargs):
        time.sleep(0.2)
        return real_log_llm_call(*args, **kwargs)

    llm_client.log_llm_call = slow_log_llm_call
    try:
        ticker_task = asyncio.create_task(ticker())
        start = time.monotonic()
        await llm_client.ask_claude("another question", purpose="general-chat")
        elapsed = time.monotonic() - start
        stop = True
        await ticker_task
    finally:
        llm_client.log_llm_call = real_log_llm_call

    check(
        f"event loop kept advancing during the (slowed) log write "
        f"(ticker ran {tick_count} times during a {elapsed:.3f}s call)",
        tick_count > 5,
    )


if __name__ == "__main__":
    asyncio.run(main())

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All log_llm_call-async (B5) regression checks passed.")
