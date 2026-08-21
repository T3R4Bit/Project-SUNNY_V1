"""Detects whether the previous run of this process crashed (a native
abort/segfault, not a normal stop or restart) by reading systemd's own
journal for this unit.

This exists because of a real, verified blind spot in the app's own
logging (logging_config.py's sunny.log): a hard native crash — glibc
"free(): invalid size"/"invalid pointer", a segfault, an OOM-kill — kills
the process before Python's logging module (or often any Python code at
all) gets to run, so it can never appear in sunny.log. Confirmed live,
2026-08-20: two real production crashes in the voice pipeline (see
voice_session.py's _patch_dave_decrypt and stt.py's new_recognizer)
showed up only in `journalctl -u sunny.service`, invisible everywhere
else the app already looks (sunny.log, health_check.py's weekly digest,
which only counts ERROR lines from that same file). Reading the journal
here closes that gap without needing a second logging pipeline.

Local dev (no systemd, no journalctl binary) always returns None — this
only means anything on the Lenovo, where the app actually runs under
systemd (see SETUP_LINUX.md's sunny.service unit).
"""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_UNIT = "sunny.service"
_CRASH_SIGNATURE_MARKERS = ("free():", "Segmentation fault", "double free", "core dumped")


def _run_journalctl() -> Optional[str]:
    """Bounded to the last hour — this only ever needs to see the run
    immediately before this one, which (per SETUP_LINUX.md's
    RestartSec=10) started at most a few minutes before this process did.
    Returns None on anything unexpected (no journalctl binary, no
    permission, timeout) rather than raising — this check is a nice-to-
    have, never allowed to block or fail startup."""
    try:
        result = subprocess.run(
            ["journalctl", "-u", SERVICE_UNIT, "--since", "1 hour ago", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug(f"crash_check: journalctl unavailable ({e}) — skipping, likely not running under systemd")
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def check_previous_crash() -> Optional[str]:
    """Isolates the journal segment for the run immediately before this
    one — between the second-to-last and the last "Started sunny.service"
    line — and returns a short, human-readable crash signature if that
    run ended abnormally, else None.

    A clean stop/restart (systemctl restart, a normal SIGTERM shutdown)
    never logs a "Main process exited" line at all — confirmed against a
    real manual restart's journal output, 2026-08-20 — so its absence is
    itself the signal that the previous run ended fine, not a gap in this
    check."""
    output = _run_journalctl()
    if not output:
        return None

    lines = output.splitlines()
    start_indexes = [i for i, line in enumerate(lines) if "Started sunny.service" in line]
    if len(start_indexes) < 2:
        return None  # no earlier run visible in this window to compare against

    segment = lines[start_indexes[-2] : start_indexes[-1]]

    exit_line = next((l for l in segment if "Main process exited" in l or "Aborted" in l), None)
    if exit_line is None or "status=0" in exit_line:
        return None

    signature_line = next(
        (l for l in segment if any(marker in l for marker in _CRASH_SIGNATURE_MARKERS)),
        exit_line,
    )
    return signature_line.split("]:", 1)[-1].strip() if "]:" in signature_line else signature_line.strip()
