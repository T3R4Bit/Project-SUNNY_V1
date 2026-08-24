"""Logs requests Sunny couldn't fulfill with real data to the Obsidian vault."""

import logging
from datetime import datetime, timezone

from sunny_code.config import get_settings

logger = logging.getLogger(__name__)


def log_unfulfilled(category: str, detail: str) -> None:
    """Append a timestamped entry to sunny-vault/log/requests.md."""
    settings = get_settings()
    log_path = settings.project_root / "sunny-vault" / "log" / "requests.md"

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = f"**{timestamp}** [{category.upper()}] {detail}\n"

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        logger.error(f"Failed to write to requests log: {e}")
