"""This block's idempotent-task + retry/backoff + structured-logging
conventions, factored into one decorator so every task module applies the
same defaults instead of re-deriving them per task. Grounded in
references/backend/celery.md's "Idempotency & acks_late" and "Retries"
sections and references/recipes/background-jobs.md's "Idempotent tasks,
retries, and not blocking the request".
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from celery.utils.log import get_task_logger

from app.celery_app import app

F = TypeVar("F", bound=Callable[..., Any])

logger = get_task_logger(__name__)


def idempotent_task(
    *,
    name: str | None = None,
    # Deliberately broad by default (see the docstring's "autoretry_for
    # defaults to (Exception,)" note below) — narrow it per task.
    autoretry_for: tuple[type[BaseException], ...] = (Exception,),
    max_retries: int = 5,
    retry_backoff: int = 5,
    retry_backoff_max: int = 600,
    **task_kwargs: Any,
) -> Callable[[F], F]:
    """Registers a task with this block's default safe-retry posture:

    - `acks_late=True` + `reject_on_worker_lost=True` — a message is only
      acked after the task finishes, so a worker crash mid-task re-queues
      it rather than silently losing it. This means the task CAN run
      twice under a crash — every task registered through this decorator
      must be safe to run twice (upsert by a stable key, not "increment a
      counter"; see celery.md's "Idempotency & acks_late").
    - `autoretry_for`/`retry_backoff`/`retry_backoff_max`/`retry_jitter` —
      declarative exponential backoff with jitter on the given exception
      types, instead of hand-rolled try/except retry loops (celery.md's
      "Retries"). Defaults retry on any Exception with 5,10,20,...,600s
      backoff, capped at 5 attempts.

      **`autoretry_for` defaults to `(Exception,)` — this is intentionally
      broad and a real project SHOULD narrow it per task.** A bare
      `Exception` also catches genuine programming errors (a `TypeError`
      from a bad argument, a `KeyError` from a malformed payload, an
      unhandled edge case in the task body itself) — those are not
      transient failures a retry will fix, and retrying one 5 times with
      backoff just delays the failure being visible while doing
      unnecessary work. Pass a narrower `autoretry_for` (e.g. the specific
      network/timeout exceptions a task's own downstream call can raise)
      once a task's real failure modes are known; this decorator's
      "override per task" contract is exactly this override.

    Usage:

        @idempotent_task(name="app.tasks.example.send_reminder")
        def send_reminder(order_id: str) -> None:
            ...  # upsert-shaped body — safe to run twice
    """

    def decorator(func: F) -> F:
        return app.task(  # type: ignore[return-value]
            func,
            name=name,
            bind=False,
            acks_late=True,
            reject_on_worker_lost=True,
            autoretry_for=autoretry_for,
            retry_backoff=retry_backoff,
            retry_backoff_max=retry_backoff_max,
            retry_jitter=True,
            max_retries=max_retries,
            **task_kwargs,
        )

    return decorator
