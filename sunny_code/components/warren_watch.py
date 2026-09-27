"""Watch Warren and notify when its status changes.

WHY THIS EXISTS
---------------
Warren halted itself with EXEC_STALE at 10:01:40 on 2026-09-23 and said
nothing. It had also halted for the same reason on 2026-09-14. Both times
the only record was a line in its own journal reading:

    ALERT (no Pushover configured -- see WARREN_PUSHOVER_*) ... reason=EXEC_STALE

Warren's alert path is Pushover, which was never configured, so every
halt it has ever raised has gone to a log nobody reads. It even prints
"alerts will only be logged, not sent. Fine for dev; not for anything
holding real capital" on every start.

Sunny already has a notification fan-out that reaches Discord, Web Push
and the Pi panel. This bridges the two, so Warren does not need Pushover
credentials to be able to reach anyone.

EDGE-TRIGGERED, NOT LEVEL-TRIGGERED
-----------------------------------
It notifies on CHANGE, never on state. A halted bot polled every couple
of minutes would otherwise produce a notification every couple of
minutes, which is how people learn to swipe alerts away without reading
them. The previous status is held in memory and compared; identical
polls are silent.

FAILING TO REACH WARREN IS ITSELF A STATUS
------------------------------------------
The API going unreachable is exactly as interesting as a halt -- both
mean the bot is not working -- so `unreachable` is a status value like
any other rather than an error that gets swallowed. It is debounced,
because a single missed poll during a restart is not news.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

import httpx

from sunny_code.components import notify
from sunny_code.config import get_settings

logger = logging.getLogger(__name__)

# Warren's read-only API binds 127.0.0.1 by design, so this only works
# from the box Warren runs on -- which is the same box Sunny runs on.
WARREN_URL = "http://127.0.0.1:5100"

POLL_SECONDS = 120

# How many consecutive failed polls before saying it is unreachable.
# Warren restarts on deploys and its own watchdog restarts; one missed
# poll is noise, three in a row over six minutes is real.
UNREACHABLE_AFTER = 3

# No independent execd-staleness check lives here. There was a
# 90-minute EXEC_STALE_MINUTES constant, never referenced by anything,
# whose comment claimed execd "is expected to beat during market
# hours". It is not: execd is a WEEKLY scheduled action (Wed 10:00 ET),
# so a 90-minute threshold would have been true for about ten minutes a
# week and wrong the rest of the time. Warren's own riskd gates its
# EXEC_STALE trip on exposure and on execd not having cleanly finished
# (warren.risk.watchdog.execd_has_settled) for exactly that reason, and
# the execd phase carried in the status below is what actually surfaces
# whether it ran.

_last: Optional[Dict] = None
_failures = 0


def _state_path() -> Path:
    return get_settings().project_root / "sunny-vault" / "data" / "state" / "warren-watch.json"


def _load_last() -> Optional[Dict]:
    """Last observed status from the previous run.

    Held on disk, not just in memory, because otherwise EVERY restart of
    sunny.service is a fresh first poll -- and a first poll on a halted
    bot alerts. Measured: 9 identical "Warren is halted" notifications in
    24 hours, one per deploy, none of them news. An alert that fires on
    something you did yourself is how people learn to ignore alerts.
    """
    path = _state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(f"warren watch state unreadable, starting fresh: {e}")
        return None


def _save_last(status: Optional[Dict]) -> None:
    from sunny_code.components import vault_io

    try:
        _state_path().parent.mkdir(parents=True, exist_ok=True)
        vault_io.atomic_write_text(_state_path(), json.dumps(status or {}, indent=2))
    except OSError as e:
        # Losing this costs one spurious notification after the next
        # restart, never correctness -- so it must not break the watcher.
        logger.warning(f"Could not persist warren watch state: {e}")


async def fetch_status() -> Optional[Dict]:
    """Warren's status as one dict, or None if it could not be reached."""
    try:
        async with httpx.AsyncClient(base_url=WARREN_URL, timeout=8) as client:
            risk = (await client.get("/risk-state")).json()
            beats = (await client.get("/heartbeats")).json()
    except Exception as e:
        logger.debug(f"warren unreachable: {type(e).__name__}")
        return None

    services = {}
    for beat in beats or []:
        name = beat.get("service")
        if name:
            services[name] = {
                "ts": beat.get("ts_utc"),
                "detail": beat.get("detail") or {},
            }

    halted = bool(risk.get("halted"))
    return {
        "status": "halted" if halted else "running",
        "halt_reason": risk.get("halt_reason") if halted else None,
        "halted_at": risk.get("halted_at") if halted else None,
        "equity": risk.get("peak_equity"),
        # execd's phase is carried because "running" and "running but in
        # shadow" are different claims -- shadow places no orders, so a
        # green light that means "not trading" would be a lie.
        "phase": (services.get("execd", {}).get("detail") or {}).get("phase"),
        "services": services,
    }


def _describe(status: Dict) -> str:
    bits = []
    if status["status"] == "halted":
        bits.append(f"reason {status['halt_reason']}")
        if status.get("halted_at"):
            bits.append(f"since {str(status['halted_at'])[:16].replace('T', ' ')}")
    if status.get("phase"):
        bits.append(f"execd phase {status['phase']}")
    if status.get("equity") is not None:
        bits.append(f"equity ${status['equity']:,.2f}")
    return " · ".join(bits)


def _changed(previous: Optional[Dict], current: Optional[Dict]) -> Optional[str]:
    """What to say about the transition, or None if nothing changed.

    Compares only the fields worth waking someone for. Heartbeat
    timestamps move constantly and are deliberately not compared, or
    every poll would be a change.
    """
    if previous is None:
        # First poll of a run. Announcing "Warren is halted" on every
        # Sunny restart would turn a deploy into an alert, so the first
        # observation only speaks if something is actually wrong.
        if current is None:
            return "Warren's API is unreachable."
        if current["status"] == "halted":
            return f"Warren is halted — {_describe(current)}"
        return None

    if current is None:
        return None  # handled by the unreachable debounce in watch()

    if previous.get("unreachable") and current:
        return f"Warren's API is back — {current['status']}. {_describe(current)}"

    if previous["status"] != current["status"]:
        if current["status"] == "halted":
            return f"Warren HALTED — {_describe(current)}"
        return f"Warren is running again. {_describe(current)}"

    if previous.get("halt_reason") != current.get("halt_reason"):
        return f"Warren's halt reason changed to {current.get('halt_reason')}"

    if previous.get("phase") != current.get("phase"):
        return (f"Warren's execd phase changed: {previous.get('phase')} "
                f"→ {current.get('phase')}")

    return None


async def poll_once() -> Optional[str]:
    """One poll. Returns the message it sent, or None."""
    global _last, _failures

    if _last is None:
        # First poll of this process: adopt whatever the previous run
        # last saw, so a restart compares against reality rather than
        # against nothing.
        _last = _load_last()

    current = await fetch_status()

    if current is None:
        _failures += 1
        if _failures == UNREACHABLE_AFTER:
            _last = {"status": "unreachable", "unreachable": True}
            await notify.send(
                "Warren unreachable",
                f"No response from the API for {UNREACHABLE_AFTER} polls.",
                url="/warren", tag="warren",
            )
            return "unreachable"
        return None

    _failures = 0
    message = _changed(_last, current)
    _last = current
    _save_last(current)

    if message:
        await notify.send("Warren", message, url="/warren", tag="warren",
                          # A halt stops trading and does not resolve on
                          # its own -- it stays up until acknowledged.
                          require_interaction=(current["status"] == "halted"))
        logger.info(f"Warren status change: {message}")
        return message
    return None


async def watch() -> None:
    """Background loop. Never raises -- a watcher that dies silently is
    worse than no watcher, since the absence of alerts then reads as
    'everything is fine'."""
    settings = get_settings()
    if not getattr(settings, "warren_watch_enabled", True):
        logger.info("Warren watch disabled")
        return

    logger.info(f"Warren watch started (every {POLL_SECONDS}s)")
    while True:
        try:
            await poll_once()
        except Exception as e:
            logger.error(f"Warren watch poll failed: {e}", exc_info=True)
        await asyncio.sleep(POLL_SECONDS)


def current_status() -> Optional[Dict]:
    """Last observed status, for a brief or a dashboard panel."""
    return _last
