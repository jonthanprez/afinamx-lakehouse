"""Centralized structured JSON logging configuration and formatter."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

# Set of standard attributes in logging.LogRecord to exclude from custom 'extra' fields
STANDARD_LOG_RECORD_ATTRIBUTES = {
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
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


def _default_json_serializer(obj: Any) -> Any:
    """Fallback serializer for objects that are not JSON-serializable by default."""
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


class JSONFormatter(logging.Formatter):
    """Custom logging formatter that outputs log records as single-line JSON (NDJSON)."""

    def format(self, record: logging.LogRecord) -> str:
        # 1. Base log structure
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno,
        }

        # 2. Extract exception information if available
        if record.exc_info:
            exc_type, exc_value, _ = record.exc_info
            log_data["exception"] = {
                "type": exc_type.__name__ if exc_type else "UnknownException",
                "message": str(exc_value),
                "stack_trace": self.formatException(record.exc_info),
            }
        elif record.exc_text:
            log_data["exception"] = {
                "stack_trace": record.exc_text,
            }

        # 3. Extract custom 'extra' fields passed to the logger
        for key, value in record.__dict__.items():
            if key not in STANDARD_LOG_RECORD_ATTRIBUTES and key not in log_data:
                log_data[key] = value

        return json.dumps(log_data, default=_default_json_serializer)


def setup_logging(
    level: Union[int, str] = logging.INFO,
    stream: Optional[Any] = None,
) -> None:
    """Configure the root logger with the structured JSONFormatter.

    Args:
        level: Logging level (e.g. logging.INFO, 'DEBUG', 'INFO').
        stream: Output stream (defaults to sys.stdout).
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to prevent duplicate output
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Convenience helper to retrieve a named logger.

    Args:
        name: Name of the logger, typically __name__.

    Returns:
        A logging.Logger instance.
    """
    return logging.getLogger(name)
