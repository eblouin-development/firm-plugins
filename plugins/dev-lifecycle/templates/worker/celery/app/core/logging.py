"""Structured (JSON) logging setup for the worker and beat processes.
Stdlib `logging` only — no new dependency — emitting one JSON object per
line so a log aggregator (CloudWatch Logs, per the infra block; anything
else in dev) can parse fields instead of grepping free-text.

Wired via Celery's own `after_setup_logger`/`after_setup_task_logger`
signals in `celery_app.py`, so both the worker's task logger and beat's
scheduler logger get the same formatter — never call `logging.basicConfig`
elsewhere in this block, it would race with Celery's own logging setup.

Every task should log through `get_task_logger(__name__)` (Celery's own
helper, re-exported by `celery_app.py`) rather than the stdlib
`logging.getLogger` directly — it binds the current task's name/id into
each record automatically once this formatter is installed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """One JSON object per log line. Never logs secrets — callers are
    responsible for not passing a secret value as a log arg (same
    discipline references/security/secure-baseline.md's "Audit logging"
    section states for the app itself); this formatter does not attempt
    to redact — see `templates/components/security/audit-logging/` for
    that concern's own dedicated `redact()` helper if a task's logging
    needs it."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Celery's task logger stashes these on the record when a task is
        # actually executing (task context) — absent for beat/worker
        # lifecycle logs, so guard with getattr rather than assuming.
        task_name = getattr(record, "task_name", None) or getattr(record, "taskName", None)
        if task_name:
            payload["task_name"] = task_name
        task_id = getattr(record, "task_id", None)
        if task_id:
            payload["task_id"] = task_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Installs the JSON formatter on the root logger once. Idempotent —
    safe to call from both `after_setup_logger` and
    `after_setup_task_logger` (Celery fires both) without double-attaching
    handlers."""
    root = logging.getLogger()
    root.setLevel(level)
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
