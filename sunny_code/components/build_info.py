"""What commit Sunny is actually running, read straight from git.

sunny_code/__init__.py has a __version__ string, but nothing bumps it per
change -- it's not a real answer to "what build is this." Git HEAD is: it
already changes on every deploy (a `git pull` on the Lenovo), so read it
fresh each call instead of maintaining a second, parallel version number
that would just drift out of sync.
"""

import logging
import subprocess

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)


def get_build_version() -> str:
    """Short commit hash + author date/time, e.g. "d56151e (08/25 11:12)" --
    or "unknown" if git isn't available (no .git, git not installed,
    timeout). Never raises; this is a status line, not load-bearing."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--date=format:%m/%d %H:%M", "--format=%h (%ad)"],
            capture_output=True, text=True, timeout=2,
            cwd=get_settings().project_root,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug(f"get_build_version: git unavailable ({e})")
        return "unknown"
    if result.returncode != 0 or not result.stdout.strip():
        return "unknown"
    return result.stdout.strip()
