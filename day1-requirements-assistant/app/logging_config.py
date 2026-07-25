"""Structured logging setup.

Provides a single `configure_logging` entry point plus a `request_id`
context variable so that every log line emitted while handling a request can be
correlated. Secrets must never be passed to the logger — the config module
exposes `redacted_api_key` for that reason.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

# Correlates all log records emitted while serving one HTTP request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Inject the current request id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", as_json: bool = False) -> None:
    """Configure the root logger. Idempotent — safe to call more than once."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Replace any pre-existing handlers so repeated calls don't duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if as_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(request_id)s | "
                "%(name)s | %(message)s"
            )
        )
    root.addHandler(handler)

    # Quiet noisy third-party loggers a notch below the app level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
