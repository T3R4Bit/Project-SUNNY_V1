"""Structured logging setup with rotating file handlers."""

import logging
import logging.handlers
import json
from pathlib import Path
from datetime import datetime
from sunny.config import get_settings


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for easy parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging():
    """Initialize logging with file rotation and structured output."""
    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level))

    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler with rotation (10MB per file, keep 10 files)
    file_handler = logging.handlers.RotatingFileHandler(
        settings.logs_dir / "sunny.log",
        maxBytes=10_000_000,
        backupCount=10,
    )
    file_handler.setLevel(getattr(logging, settings.log_level))

    if settings.log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler (dev only)
    if settings.debug:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    return root_logger


logger = logging.getLogger(__name__)
