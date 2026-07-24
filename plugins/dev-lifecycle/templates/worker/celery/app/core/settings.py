"""This block's settings module: `templates/components/backend/settings/
settings.py`'s `AppSettings` (byte-identical below the header note — see
that component's own docstring for the full rationale), extended with the
Celery/Redis fields this worker needs and unavailable on the shared base.
Pydantic v2 + pydantic-settings, pinned per
references/compatibility-matrix.md's Backend — Python row.

Kept in sync via the weekly freshness audit (Stage 12, #35) — never
hand-edit `AppSettings` itself below the vendored-file convention; edit
`templates/components/backend/settings/settings.py` and re-sync. The
`WorkerSettings` subclass below is new, worker-specific code, not part of
the vendored surface.

A project's `apps/api` and `apps/worker` construct settings independently
(two processes, two `Settings()` calls) — they share `DATABASE_URL`
because the operator sets it identically in both environments, not
because either app imports the other's settings module. This is the same
shared-DATABASE_URL wiring `references/recipes/background-jobs.md`
describes for the Django+Celery track, generalized to whichever backend
this worker sits alongside.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Vendored, byte-identical (below this note) to
    templates/components/backend/settings/settings.py's AppSettings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False

    # Required — no default. Same DATABASE_URL the backend block reads;
    # a worker without it fails at WorkerSettings() construction (process
    # startup), not on the first task that touches the database.
    database_url: str

    cors_allowed_origins: list[str] = Field(default_factory=list)


class WorkerSettings(AppSettings):
    """This block's real settings class — `AppSettings` plus the
    broker/result-backend/beat config Celery needs. Construct exactly
    once per process (`celery_app.py` does this at import time) and read
    every field from it; never read `os.environ` directly elsewhere in
    this block."""

    # Required — no default, matching AppSettings.database_url's own
    # fail-fast posture. Points at the SAME Redis instance the backend
    # block's rate-limiting/caching would use if wired (a separate DB
    # index — see broker/result_backend split below), or the monorepo
    # compose's shared `redis` service in dev.
    celery_broker_url: str = Field(
        description="Redis URL for the Celery broker, e.g. redis://redis:6379/0. Required.",
    )

    # Optional: only needed if a task's return value is actually consumed
    # (celery.md's "Broker vs result backend" — don't wire a result
    # backend a project never reads from). Separate DB index from the
    # broker when both are set, per that same doc's convention.
    celery_result_backend: str | None = Field(
        default=None,
        description="Redis URL for the Celery result backend, e.g. redis://redis:6379/1. "
        "Optional — leave unset if no task's return value is consumed.",
    )

    # Isolate slow/IO-bound tasks onto their own queue (celery.md's
    # "Routing & queues") without hardcoding the name in task code.
    celery_default_queue: str = "celery"
    celery_io_queue: str = "io"

    # worker_prefetch_multiplier=1 for long-running tasks (celery.md's
    # "Workers & concurrency") — the default (4) is tuned for short tasks
    # and can starve a worker behind one slow one at the default of 4.
    celery_worker_prefetch_multiplier: int = 1

    # Structured logging level for this process (worker or beat) — kept
    # here rather than a bare LOG_LEVEL env read so it goes through the
    # same fail-fast validation as every other setting.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
