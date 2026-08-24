"""Crash detection + reporting for the Sunny Companion device's own services.

The device has no Discord credentials of its own (kept server-side only --
see sunny-companion/README.md's security note on the Anthropic Admin API
key, same posture applies here), so it can't post to Discord directly the
way the main server's own crash notice does (crash_check.py + discord_bot.py
on the server). Instead: a marker file records "a service is currently
running"; if that marker is still there the *next* time the service starts,
the previous run never shut down cleanly (systemd's Restart=on-failure fired,
same as a native crash on the main server) -- report that to the server's
POST /api/pi/crash-report, which relays it to Discord's #warnings channel.

Usage in each Pi service's entry point:

    from crash_reporter import report_crash_if_needed, mark_running, mark_clean_shutdown

    report_crash_if_needed("sunny-face", SERVER_URL)
    mark_running("sunny-face")
    try:
        main_loop()
    finally:
        mark_clean_shutdown("sunny-face")
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

MARKER_DIR = Path("/run/sunny-companion")  # tmpfs on the Pi -- cleared on power loss too,
# which is fine: a power-loss reboot isn't a "crash to alert on" in the sense this cares
# about, and there's no server to report to during the boot that would detect it anyway.


def _marker_path(service_name: str) -> Path:
    return MARKER_DIR / f"{service_name}.running"


def mark_running(service_name: str) -> None:
    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    _marker_path(service_name).write_text("running")


def mark_clean_shutdown(service_name: str) -> None:
    _marker_path(service_name).unlink(missing_ok=True)


def report_crash_if_needed(service_name: str, server_url: str, timeout: float = 3.0) -> None:
    """Call once at startup, before mark_running(). No-ops (and never
    raises) if the marker isn't there (normal clean start) or if the server
    can't be reached (device may not have network yet at boot -- this is a
    nice-to-have alert, never allowed to block or fail startup)."""
    marker = _marker_path(service_name)
    if not marker.exists():
        return
    try:
        requests.post(
            f"{server_url.rstrip('/')}/api/pi/crash-report",
            json={"device": service_name, "reason": "restarted without a clean shutdown"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        logger.warning(f"crash_reporter: couldn't reach server to report {service_name}'s crash: {e}")
