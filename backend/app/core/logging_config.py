"""Structured JSON logging for auditability.

The platform must log all actions. We emit single-line JSON to stdout so the
records can be shipped to any log aggregator while remaining human-readable.
Domain/audit events additionally go to the database via `AuditLog`.
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach any structured extras passed via `logger.info(..., extra={...})`.
        for key, value in getattr(record, "__dict__", {}).items():
            if key in ("args", "msg", "levelname", "name") or key.startswith("_"):
                continue
            if key not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Quiet noisy third-party loggers.
    for noisy in ("uvicorn.access", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
