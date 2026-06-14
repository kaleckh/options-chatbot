from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


LOGGER_NAME = "options_backend"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value.tzinfo else value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        structured = getattr(record, "structured", None)
        if isinstance(structured, dict):
            payload.update(_json_safe(structured))
        if record.exc_info:
            exc_type = record.exc_info[0]
            exc_value = record.exc_info[1]
            payload["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else None,
                "traceback": "".join(traceback.format_exception(*record.exc_info)).rstrip(),
            }
        return json.dumps(payload, sort_keys=True)


def _coerce_level(raw: str | int | None) -> int:
    if isinstance(raw, int):
        return raw
    normalized = str(raw or os.getenv("OPTIONS_BACKEND_LOG_LEVEL") or "INFO").strip().upper()
    return int(getattr(logging, normalized, logging.INFO))


def configure_logging(
    *,
    stream: TextIO | None = None,
    level: str | int | None = None,
    force: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers and not force:
        logger.setLevel(_coerce_level(level))
        return logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(_coerce_level(level))
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
