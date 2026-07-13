from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION, __version__
from .observability import redact


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
        }
        for name in (
            "request_id", "project_id", "commit_id", "operation", "duration_ms",
            "result", "retryability", "error_code",
        ):
            value = getattr(record, name, None)
            if value is not None:
                fields[name] = value
        if record.exc_info:
            fields["exception"] = self.formatException(record.exc_info)
        return json.dumps(redact(fields), ensure_ascii=False, separators=(",", ":"))


def configure_runtime_logging(path: Path | None, max_bytes: int, backups: int) -> logging.Logger:
    logger = logging.getLogger("story_runtime")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if getattr(logger, "_hybrid_configured", False):
        return logger
    handler: logging.Handler
    if path is None:
        handler = logging.StreamHandler()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    setattr(logger, "_hybrid_configured", True)
    return logger
