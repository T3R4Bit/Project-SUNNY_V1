"""Structured logging module for Project SUNNY."""

import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logging(name: str = "sunny", level: int = logging.INFO) -> logging.Logger:
    """
    Set up structured logging with rotating file handler and console output.

    Args:
        name: Logger name
        level: Logging level (default INFO)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Format: timestamp | level | message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Rotating file handler (logs/ folder, daily rotation, 30-day retention)
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=30,  # Keep 30 rotated files = ~30 days
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Module-level logger
logger = setup_logging("sunny")
