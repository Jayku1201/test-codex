"""Logging configuration helpers."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict

from app.core.config import Settings


class JSONLogFormatter(logging.Formatter):
    """Format log records as JSON strings."""

    def __init__(self, app_env: str) -> None:
        super().__init__()
        self.app_env = app_env
        self._reserved = {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
        }

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - short description inherited
        log_record: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": self.app_env,
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in self._reserved:
                continue
            log_record[key] = value

        return json.dumps(log_record, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    """Configure application logging to emit JSON formatted logs."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter(settings.app_env))

    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.setLevel(logging.INFO)
