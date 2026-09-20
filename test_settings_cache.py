#!/usr/bin/env python
"""Regression tests for get_settings()'s TTL cache (plan item A3).

Proves two things: (1) repeated calls within the TTL window return a cached
instance rather than re-parsing .env every time, and (2) an edited env var
is still picked up automatically once the TTL elapses - the "no restart
needed" contract is preserved, just not instant. Plain assert-based script,
matching the style of test_routing_fixes.py.
"""

import os
import sys

import sunny_code.config as config_module

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def test_caches_within_ttl():
    config_module._settings_cache = None
    os.environ["APP_NAME"] = "Before Edit"

    first = config_module.get_settings()
    check("first call picks up current env var", first.app_name == "Before Edit")

    # Edit the env var directly (no .env file involved - Settings reads
    # process env too) without advancing the clock: same cached instance,
    # so this must NOT be picked up yet.
    os.environ["APP_NAME"] = "After Edit (still within TTL)"
    second = config_module.get_settings()
    check("second call within TTL returns cached instance", second is first)
    check("second call within TTL still reports the old value", second.app_name == "Before Edit")


def test_reload_after_ttl_elapses():
    config_module._settings_cache = None
    os.environ["APP_NAME"] = "Pre-TTL Value"
    first = config_module.get_settings()
    check("baseline call succeeds", first.app_name == "Pre-TTL Value")

    os.environ["APP_NAME"] = "Post-TTL Value"
    # Simulate TTL elapsing without a real sleep: backdate the cached
    # timestamp past the TTL window.
    cached, cached_at = config_module._settings_cache
    config_module._settings_cache = (cached, cached_at - config_module._SETTINGS_TTL_SECONDS - 0.01)

    third = config_module.get_settings()
    check("call after TTL elapses is not the cached instance", third is not first)
    check("call after TTL elapses picks up the live-edited env var", third.app_name == "Post-TTL Value")


if __name__ == "__main__":
    test_caches_within_ttl()
    test_reload_after_ttl_elapses()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All get_settings() TTL-cache regression checks passed.")
