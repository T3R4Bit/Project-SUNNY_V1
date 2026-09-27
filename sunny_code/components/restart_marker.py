"""Tell a deliberate restart apart from a crash.

WHY
---
A restart and a crash look identical from inside the process that comes
back: both are "the last run ended and this one started". So an
unqualified "restarted" notification reads as an alarm even when someone
just deployed, and after a few of those the real ones get ignored.

The distinction cannot be inferred after the fact -- it has to be
recorded BEFORE the restart, by whoever is doing it. That is what this
is: a one-line marker written deliberately, consumed once on startup.

CONTRACT
--------
- Marker present on startup  -> this was intentional. Say "restarted",
  quietly, and only if anything needs saying at all.
- Marker absent on startup   -> nobody announced it. Fall back to the
  existing crash detection (crash_check reads systemd's journal for a
  real native crash signature) and say nothing if that finds nothing.

FAIL OPEN, NOT LOUD
-------------------
Every failure path here returns "not an intentional restart". Getting
that wrong means one alert that should have been quiet, which is a far
better outcome than suppressing a real crash because a marker file was
left behind by something that never restarted.

The marker is consumed -- read and deleted in one step -- so it can only
ever explain ONE restart. A stale marker silencing every future crash is
exactly the failure this must not have.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Marker older than this is ignored. A deploy restarts within seconds;
# anything claiming to explain a restart an hour later is a leftover, and
# trusting it would silence a genuine crash.
MAX_AGE = timedelta(minutes=10)


def _path(service: str = "sunny") -> Path:
    from sunny_code.config import get_settings

    # Alongside the other runtime state, NOT in the synced part of the
    # vault -- this is a transient file written and deleted seconds apart
    # and has no business crossing devices.
    return get_settings().logs_dir / f"{service}.restarting"


def mark_intentional(reason: str = "deploy", service: str = "sunny") -> bool:
    """Record that the restart about to happen is deliberate.

    Call this BEFORE restarting. Returns False if it could not be
    written, in which case the restart will simply be reported the old
    way rather than failing.
    """
    try:
        path = _path(service)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{datetime.now().isoformat(timespec='seconds')}\n{reason}\n",
                        encoding="utf-8")
        return True
    except OSError as e:
        logger.warning(f"Could not write restart marker: {e}")
        return False


def consume(service: str = "sunny") -> Optional[str]:
    """The reason for this restart if it was deliberate, else None.

    Reads and DELETES in one step. A marker that survives its own restart
    would explain every subsequent one, including a real crash -- which
    is the one thing this must never do.
    """
    path = _path(service)
    if not path.exists():
        return None

    reason = None
    try:
        raw = path.read_text(encoding="utf-8").strip().splitlines()
        stamp = datetime.fromisoformat(raw[0]) if raw else None
        reason = raw[1] if len(raw) > 1 else "deploy"
        if stamp is None or datetime.now() - stamp > MAX_AGE:
            logger.info("Restart marker is stale, treating restart as unexplained")
            reason = None
    except (OSError, ValueError, IndexError) as e:
        logger.warning(f"Restart marker unreadable: {e}")
        reason = None
    finally:
        # Deleted whatever happened, including on a parse failure -- a
        # marker that cannot be read is still a marker that must not
        # linger.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    return reason


def startup_notice(service: str = "sunny") -> Optional[str]:
    """What (if anything) to say about how this run started.

    Returns None for the common case -- a clean start nobody needs
    telling about. Only a real crash is worth interrupting for; a
    deliberate restart is logged and otherwise silent.
    """
    reason = consume(service)
    if reason is not None:
        # Deliberate. Logged so the journal still records it, but nothing
        # is pushed -- you already know, you did it.
        logger.info(f"Started after an intentional restart ({reason})")
        return None

    from sunny_code.components import crash_check

    crash = crash_check.check_previous_crash()
    if crash:
        return f"Sunny crashed and restarted — {crash}"
    return None
