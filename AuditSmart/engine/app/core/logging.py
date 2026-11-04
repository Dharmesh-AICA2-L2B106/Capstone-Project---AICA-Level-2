"""Structured JSON logging that can never carry ledger rows or party names.

Only whitelisted keys passed via ``extra=`` are emitted; the message text is scrubbed of
TRN-like numbers, e-mail addresses, IBANs and phone numbers as a second line of defence.
Use ``log_event("dataset.parsed", dataset_id=..., rows=...)`` rather than formatting values
into messages.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

ALLOWED_FIELDS = frozenset(
    {
        "event", "dataset_id", "job_id", "engagement_id", "upload_id", "rows", "row_count",
        "chunks", "bytes", "sha256", "status", "status_code", "method", "path", "duration_ms",
        "user_ref", "errors", "warnings", "critical", "engine_version", "error_type", "progress",
    }
)

_SCRUBBERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[iban]"),
    (re.compile(r"\b784-?\d{4}-?\d{7}-?\d\b"), "[emirates-id]"),
    (re.compile(r"\d{10,}"), "[number]"),
    (re.compile(r"\+?\d[\d\s-]{8,}\d"), "[phone]"),
)

_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message"}


def scrub(text: str) -> str:
    for pattern, repl in _SCRUBBERS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS:
                continue
            if key in ALLOWED_FIELDS:
                payload[key] = scrub(str(value)) if isinstance(value, str) else value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__  # never the message (may hold data)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_auditsmart", False):
            root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._auditsmart = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


logger = logging.getLogger("auditsmart")


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log an event with whitelisted fields only (others are silently dropped)."""
    safe = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS and k != "event"}
    logger.log(level, event, extra={"event": event, **safe})
