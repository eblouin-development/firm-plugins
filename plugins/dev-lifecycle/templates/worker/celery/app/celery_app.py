"""The Celery app factory this block builds around — `celery -A app.celery_app
worker` and `celery -A app.celery_app beat` both point here. Per
references/backend/celery.md's "App setup & autodiscovery" and
references/recipes/background-jobs.md's Django wire-up steps, generalized
to run standalone (this block is not itself a Django app — see the
"Beat scheduler" section of this block's README for the DB-backed
scheduler swap a Django-backed project can opt into).

Config keys are lowercase on the Celery `Celery.conf` object (broker_url,
result_backend, ...) since Celery 4.0 — this module sets them directly
rather than via `config_from_object`, since there is no Django settings
module to bridge from by default.
"""

from __future__ import annotations

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger, worker_process_init

from app.core.db.session import configure_engine
from app.core.logging import configure_logging
from app.core.settings import WorkerSettings

settings = WorkerSettings()

app = Celery("worker")

def _route_task(name: str, args: object, kwargs: object, options: object, task=None, **kw: object) -> dict[str, str] | None:
    """Isolates slow/IO-bound tasks onto their own queue by NAME
    convention (celery.md's "Routing & queues") rather than a per-task
    hardcoded `queue=` kwarg at every call site: a task function named
    `io_<something>` (see tasks/example.py's `io_send_notification`)
    routes to `settings.celery_io_queue` automatically; everything else
    stays on the default queue."""
    task_func_name = name.rsplit(".", 1)[-1]
    if task_func_name.startswith("io_"):
        return {"queue": settings.celery_io_queue}
    return None


app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    # json only — never accept pickle from an untrusted broker (celery.md's
    # "Serialization & security"; also references/security/secure-baseline.md).
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue=settings.celery_default_queue,
    task_routes=(_route_task,),
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    # Bounded growth on result storage (celery.md's "Result backend
    # caveats") — only meaningful when celery_result_backend is set.
    result_expires=86400,
    # Beat: file-based PersistentScheduler by default (no external DB
    # dependency, works with either backend track) — see this block's
    # README "Beat scheduler" section for the django-celery-beat swap.
    beat_schedule={},
)

# Picks up every @shared_task-decorated callable in app.tasks.* without
# each module needing to import `app` directly (avoids circular imports —
# celery.md's "Defining tasks").
app.autodiscover_tasks(["app.tasks"])


@worker_process_init.connect
def _init_worker_process(**_: object) -> None:
    """Runs once per forked worker process (celery.md's "Workers &
    concurrency" — the prefork pool forks after this app module is
    imported once in the parent). Configures THIS process's own DB engine
    — an `AsyncEngine`/connection pool created before a fork is unsafe to
    reuse after one, so the engine is deliberately configured here, not
    at module import time, mirroring the "fresh event loop per task"
    posture in task_session.py."""
    configure_engine(settings.database_url)


@after_setup_logger.connect
@after_setup_task_logger.connect
def _init_logging(**_: object) -> None:
    configure_logging(settings.log_level)
