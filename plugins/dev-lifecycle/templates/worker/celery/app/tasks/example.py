"""Example task module — the pattern a real project's `app/tasks/*.py`
follows: import `idempotent_task` from `base.py`, write an upsert-shaped
body (safe to run twice under `acks_late`), and pass **IDs, not ORM
objects** as arguments (celery.md's "Pitfalls & testing" — an ORM object
serializes stale and bloats the message; re-fetch inside the task).

Delete or replace this module in a real project; it exists so
`tests/test_tasks.py` has something concrete to exercise and so a new
task author has a working example to copy rather than starting from a
blank file.
"""

from __future__ import annotations

from celery.utils.log import get_task_logger
from sqlalchemy import text

from app.core.db.task_session import run_async, task_db_session
from app.tasks.base import idempotent_task

logger = get_task_logger(__name__)


@idempotent_task(name="app.tasks.example.record_event")
def record_event(event_id: str, payload: dict) -> str:
    """Default-queue example: upserts a row by `event_id` (the stable
    key that makes this safe to run twice under `acks_late`). Runs the
    actual async DB work through `run_async`/`task_db_session` — see
    task_session.py's docstring for why a task needs its own event loop
    rather than reusing one across calls.

    Returns the event_id so a caller using `.apply_async()` with a result
    backend configured can confirm what ran; the return value is otherwise
    unused (celery.md's "Result backend caveats" — don't lean on results
    for coordination)."""
    logger.info("recording event", extra={"event_id": event_id})
    return run_async(_record_event(event_id, payload))


async def _record_event(event_id: str, payload: dict) -> str:
    async with task_db_session() as db:
        # Placeholder body: a real project replaces this with an actual
        # upsert against a real model (SQLAlchemy 2.0 `insert(...)
        # .on_conflict_do_update(...)` for Postgres, or a plain
        # get-or-create pattern). No models are vendored into this block
        # — it consumes whatever models the backend block that composes
        # alongside it already defines.
        await db.execute(text("SELECT 1"))
    return event_id


@idempotent_task(name="app.tasks.example.io_send_notification")
def io_send_notification(user_id: str, message: str) -> None:
    """IO-queue example: the `io_` name prefix routes this task to
    `settings.celery_io_queue` automatically (see celery_app.py's
    `_route_task`) — a burst of slow notification sends can't starve
    fast default-queue tasks. Fire-and-forget: logs and returns, matching
    background-jobs.md's "catch and log its own errors; never propagate
    into a place nothing awaits it" discipline for non-critical side
    effects, layered on top of this task's own `autoretry_for` for the
    retryable failure modes that DO matter (a flaky downstream call)."""
    logger.info("sending notification", extra={"user_id": user_id})
    # A real project calls an email/push provider here.
