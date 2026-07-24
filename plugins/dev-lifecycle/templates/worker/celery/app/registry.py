"""The enqueue/task-registration seam this block exposes to BOTH backend
blocks (composition contract — see README.md). A producer (an
`app/api` route or view in `backend/fastapi`/`backend/django`) does NOT
need to import this worker's task function code to dispatch work — Celery
producers only need a broker connection and the target task's registered
NAME, per Celery's own client/worker decoupling model. That's what makes
this a real seam rather than a hidden coupling: `apps/api` and
`apps/worker` are two separate deployables (two Dockerfiles, two
processes) with no shared Python package between them, so the producer
side is deliberately this thin, dependency-light module — copy it into
the consuming backend block's own `app/core/tasks/registry.py` (or
equivalent) rather than trying to import `apps/worker` as a library.

    from app.core.tasks.registry import TaskName, enqueue

    @router.post("/events")
    async def create_event(payload: EventCreate) -> EventOut:
        event = await repo.create(**payload.model_dump())
        enqueue(TaskName.RECORD_EVENT, str(event.id), payload.model_dump())
        return EventOut.model_validate(event)

`TaskName` is a plain namespace of the exact dotted task names
`celery_app.py`'s `app.autodiscover_tasks(["app.tasks"])` registers (each
task in `tasks/*.py` sets its own `name=` explicitly via
`idempotent_task(name=...)` — see base.py) — a shared source of truth so a
producer never hand-types a task-name string prone to a silent typo (a
misspelled task name fails at ENQUEUE time with an unknown-task error only
if the broker/worker validates it, which Celery does not do by default —
`send_task` will happily enqueue a message no worker task matches, and
it silently sits unconsumed. Import `TaskName` and call `enqueue()` with
its constants, not a raw string, to avoid this failure mode entirely).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from celery import Celery


class TaskName:
    """Every task this block registers, by its exact `name=`. Extend this
    alongside adding a new task in `tasks/*.py` — the two must stay in
    sync (a task-name-conformance test in `tests/test_registry.py`
    enforces this within the block itself; a consuming backend that
    copies this file is responsible for keeping its own copy in sync,
    same as any other vendored file in this kit)."""

    RECORD_EVENT = "app.tasks.example.record_event"
    IO_SEND_NOTIFICATION = "app.tasks.example.io_send_notification"


@lru_cache(maxsize=1)
def _producer_app() -> Celery:
    """A minimal Celery client app — broker connection only, no task
    modules imported, no result backend required to enqueue (only to read
    a result back). Reads `CELERY_BROKER_URL` directly from the process
    environment rather than through either app's own `Settings` class —
    this module is meant to be copy-paste portable into either backend
    block without pulling in `WorkerSettings`/`AppSettings` as a
    dependency. Cached (module-level, via `lru_cache`) so a producer
    process builds exactly one client connection, reused across
    requests — same "configure once, read many times" posture
    `db-session/session.py`'s `configure_engine` follows."""
    broker_url = os.environ.get("CELERY_BROKER_URL")
    if not broker_url:
        raise RuntimeError(
            "CELERY_BROKER_URL is not set — cannot enqueue a task. Set it to the same "
            "Redis broker URL the worker block's WorkerSettings.celery_broker_url reads."
        )
    return Celery("producer", broker=broker_url)


def enqueue(
    task_name: str,
    *args: Any,
    queue: str | None = None,
    countdown: int | None = None,
    **kwargs: Any,
) -> Any:
    """Dispatches `task_name` (a `TaskName` constant) via
    `Celery.send_task` — the by-name equivalent of calling
    `some_task.delay(...)` from inside the worker process itself, usable
    from a process that never imported the task function. Returns an
    `AsyncResult` handle (usable only if `celery_result_backend` is
    configured on the worker side — see WorkerSettings; otherwise its
    `.get()` will hang/error, matching Celery's own documented behavior
    with no result backend). Never call the task's underlying Python
    function directly from a producer — there isn't one to call from this
    module by design; `send_task` is the only path, which is itself the
    guardrail against accidentally running it in-process."""
    return _producer_app().send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        countdown=countdown,
    )


def _reset_producer_for_tests() -> None:
    """Test-only hook: clears the cached producer client between tests.
    Mirrors session.py's `_reset_engine_for_tests()` pattern."""
    _producer_app.cache_clear()
