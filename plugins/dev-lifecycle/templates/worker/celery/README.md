<!--
block: worker/celery
needs: a backend block already in apps/api (shared DATABASE_URL); CELERY_BROKER_URL (required); CELERY_RESULT_BACKEND (optional); a reachable Redis instance; Python 3.13 + uv — see "Composition contract" below
exposes: the Celery app + autodiscovered tasks; the enqueue/TaskName seam (app/registry.py) both backends copy in; a beat scheduler; liveness/readiness via app/health.py; its doc fragment — see "Composition contract" below
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-24
provenance: manual
-->

# worker/celery

The Celery worker block: an app factory, task-module conventions
(idempotent + retry/backoff + structured logging), a beat scheduler, and
an enqueue seam both backend blocks call — closing the gap
`references/recipes/background-jobs.md` used to describe as a "project
addition" on the FastAPI track. Lives at `templates/worker/celery/` in
this repo; scaffolding materializes it into a project's `apps/worker/`,
composing **alongside** whichever backend block (`backend/fastapi` or
`backend/django`) is already in `apps/api/` — this is not itself an
alternative in a shared slot the way the two backend blocks are
alternatives to each other.

First-class for `backend/fastapi` (which has no other task-queue story)
and consistent with `backend/django`'s existing Celery posture
(`references/backend/celery.md`, `references/recipes/background-jobs.md`)
— the same config-key casing, `acks_late`/idempotency discipline,
declarative-retry pattern, and queue-routing convention that recipe
already documents for the Django track, generalized into a real, runnable
worker process instead of "add Celery to your Django project yourself."

## Contents
- Composition contract
- App layout
- Task conventions: idempotent + retry/backoff + structured logging
- The enqueue seam (how a backend calls in)
- Beat scheduler
- Health / liveness
- Dev run (Docker)
- Testing
- Security
- Maintenance

## Composition contract

**NEEDS**
- **A backend block already materialized** (`apps/api/`) — this block
  reads the SAME `DATABASE_URL` that backend uses (two processes, one
  Postgres instance) and follows the same async-driver-scheme convention
  `db-session/` enforces. It is not meant to run against a database no
  backend also reads from.
- **`DATABASE_URL`** — async driver scheme, exactly as `db-session/`'s
  `configure_engine()` requires (fails fast on a bare sync scheme).
- **`CELERY_BROKER_URL`** — required, `redis://...`. **`CELERY_RESULT_BACKEND`**
  — optional, only set it if a task's return value is actually consumed
  (`references/backend/celery.md`'s "Result backend caveats").
- **A reachable Redis instance** — this block's own `docker-compose.yml`
  (`redis` service) for standalone dev, or the monorepo root
  `docker-compose.yml`'s shared `redis` service once this block is wired
  into a full project (see that file's own comments).
- **Python 3.13.x + uv.**

**EXPOSES**
- The Celery app — `app.celery_app.app` — and every task registered under
  `app/tasks/`, autodiscovered via `app.autodiscover_tasks(["app.tasks"])`.
- **The enqueue/task-registration seam** (`app/registry.py`): `TaskName`
  (the dotted names of every registered task) + `enqueue(name, *args,
  **kwargs)`, a thin Celery **producer** client (broker connection only,
  no task code imported) — copy this file into either backend block's own
  `app/core/tasks/registry.py` (or equivalent) so a route/view can
  dispatch work without importing this block as a library. See "The
  enqueue seam" below.
- A beat scheduler process, `celery -A app.celery_app beat`.
- Liveness/readiness: `python -m app.health worker` / `python -m app.health
  beat` — see "Health / liveness".
- Its co-located doc fragment: `docs/fragment.md`.

## App layout

```
apps/worker/
  app/
    celery_app.py        # the Celery() instance, config, autodiscovery, signals
    registry.py           # TaskName + enqueue() — the producer-side seam
    health.py              # python -m app.health {worker,beat}
    core/
      settings.py          # WorkerSettings(AppSettings) — broker/backend/queue config
      logging.py            # JSON structured-logging formatter
      db/
        session.py           # vendored, byte-identical to components/backend/db-session
        task_session.py       # sync-task <-> async-session bridge (run_async/task_db_session)
    tasks/
      base.py               # idempotent_task() — the acks_late + retry/backoff decorator
      example.py             # a worked example: a default-queue and an io_-queue task
  tests/
  docs/fragment.md
  Dockerfile
  docker-compose.yml
  pyproject.toml
```

## Task conventions: idempotent + retry/backoff + structured logging

Every task in this block is written through `tasks/base.py`'s
`idempotent_task()` decorator, not `@app.task` by hand, so the same safe
defaults apply everywhere:

- **`acks_late=True` + `reject_on_worker_lost=True`** — a message is only
  acked once the task finishes; a worker crash mid-task re-queues it. This
  means a task CAN run twice under a crash — every task body must be
  **idempotent** (upsert by a stable key — `tasks/example.py`'s
  `record_event(event_id, ...)` — not "increment a counter"). See
  `references/backend/celery.md`'s "Idempotency & acks_late".
- **Declarative retries** — `autoretry_for`, `retry_backoff=5`,
  `retry_backoff_max=600`, `retry_jitter=True`, `max_retries=5` by
  default (override per task): exponential backoff with jitter, never a
  hand-rolled `try`/`except` retry loop.
- **Structured (JSON) logging** — `app/core/logging.py`'s `JsonFormatter`
  is installed on Celery's own `after_setup_logger`/
  `after_setup_task_logger` signals (`celery_app.py`), so every task logs
  through `celery.utils.log.get_task_logger(__name__)` and gets one JSON
  line per record with `task_name`/`task_id` bound in automatically.
  Never log a secret or full PII payload — same rule
  `references/security/secure-baseline.md`'s "Audit logging" section
  states for the app itself.
- **Queue routing by name convention** — a task named `io_<something>`
  (see `tasks/example.py`'s `io_send_notification`) routes to the
  dedicated IO queue automatically (`celery_app.py`'s `_route_task`),
  isolating slow/IO-bound work from fast default-queue tasks without a
  per-call `queue=` kwarg at every dispatch site
  (`references/backend/celery.md`'s "Routing & queues").
- **IDs, not ORM objects, as task arguments** — `record_event(event_id: str,
  ...)`, never `record_event(event_object)`; an ORM object serializes
  stale and bloats the message (celery.md's "Pitfalls & testing"). Task
  args must be JSON-serializable (`task_serializer`/`accept_content` are
  pinned to `json`, never `pickle` — arbitrary code execution risk on
  deserialize from an untrusted broker).
- **Async DB access from a synchronous task body** —
  `app/core/db/task_session.py`'s `run_async()`/`task_db_session()`
  bridges this block's vendored async `session.py` (SQLAlchemy
  `AsyncSession`) into Celery's synchronous execution model: a fresh
  `asyncio.run()` per task call, never a loop reused across calls or
  across a prefork boundary. See that module's own docstring for why.

## The enqueue seam (how a backend calls in)

`apps/worker` and `apps/api` are two separate deployables (two
Dockerfiles, two processes) with no shared Python package between them —
so a backend route does NOT import this block's task functions directly.
Instead, copy `app/registry.py` into the backend block's own
`app/core/tasks/registry.py` (or equivalent) and call:

```python
from app.core.tasks.registry import TaskName, enqueue

@router.post("/events")
async def create_event(payload: EventCreate) -> EventOut:
    event = await repo.create(**payload.model_dump())
    enqueue(TaskName.RECORD_EVENT, str(event.id), payload.model_dump())
    return EventOut.model_validate(event)
```

`enqueue()` uses `Celery.send_task(name, args, kwargs)` — a producer only
needs the broker URL and the exact registered task name (`TaskName`'s
constants, not a hand-typed string prone to a silent typo that Celery
does not validate at enqueue time). This is the SAME pattern
`references/recipes/background-jobs.md`'s Django wire-up already
describes (`.delay()`/`.apply_async()`, never call a task function
directly) — `enqueue()` is the cross-process equivalent for a producer
that never imported the task code at all.

## Beat scheduler

`celery_app.py` wires Celery's own file-based `PersistentScheduler`
(the default; `beat_schedule={}` — a project fills this dict with its
own periodic entries) so beat runs with **no external DB dependency**,
working identically whether this block sits next to `backend/fastapi` or
`backend/django`.

A project on the Django track that wants schedules editable via Django
admin (rather than committed as code) can opt into
`django-celery-beat`'s DB-backed `DatabaseScheduler` instead — add
`django_celery_beat` to that block's `INSTALLED_APPS`, migrate, and pass
`--scheduler django_celery_beat.schedulers:DatabaseScheduler` to the
`beat` command (`docker-compose.yml`'s `beat` service `command:`) — see
`references/backend/celery.md`'s "Periodic tasks (django-celery-beat)".
This block does not hard-depend on `django-celery-beat` in its own
`pyproject.toml` — that would break the FastAPI track it's first-class
for.

**Run exactly one `beat` process** — never scale `docker-compose.yml`'s
`beat` service; two beats double-fire every scheduled task
(`references/backend/celery.md`'s own operational invariant). The
`worker` service IS safe to scale.

## Health / liveness

Celery ships no HTTP server for either process, so this block's liveness
story is a CLI probe (`app/health.py`), wired into the Dockerfile's
`HEALTHCHECK` — a DIFFERENT one per process, on DIFFERENT build stages
(`prod` for worker, `beat` for beat — see Dockerfile's own header note):

- **worker**: pings ONLY this container's own node
  (`celery@<hostname>` — Celery's default nodename scheme) — exits 0 if
  THAT specific node answers within 5s. Deliberately NOT an unscoped
  `inspect ping` (which broadcasts to and collects replies from every
  worker on the shared broker): `worker` scales horizontally
  (`docker compose up --scale worker=N`, all replicas on one broker), so
  an unscoped ping would let a dead replica see a live sibling's reply
  and report itself healthy — a false-healthy result the orchestrator
  would never catch. See `app/health.py`'s module docstring for the full
  rationale.
- **beat**: checks the on-disk `celerybeat-schedule` file's mtime is
  recent (beat has no broker-facing ping of its own, and pinging a node
  name at all would be meaningless for a process that isn't a worker).

Because the probe differs per process, **a `beat` deployment must build
the Dockerfile's `beat` stage explicitly (`--target beat`)** — the
default (`prod`) stage's `HEALTHCHECK` is the worker probe, which a beat
process would never satisfy. `docker-compose.yml` in this block instead
runs both processes off the `dev` stage (no `HEALTHCHECK` at all there —
see Dockerfile), so this only matters for a real (non-compose)
deployment path, e.g. the infra block's ECS task definition, which must
wire `python -m app.health worker` / `python -m app.health beat` into
each task definition's own `healthCheck` block matching which process it
runs — see `docs/fragment.md`'s "Deployment" section.

## Dev run (Docker)

`docker compose up --build` inside `apps/worker/` boots `db` (Postgres,
port 5433 — offset from the backend block's 5432 so both run side by
side standalone), `redis`, `worker`, and `beat` — this block's own
self-contained dev stack (see `docker-compose.yml`'s header comment for
how this differs from the monorepo root compose file's SHARED `redis`
service once this block is wired into a full project). `just dev`
(`templates/monorepo/justfile`) boots this alongside `apps/api`'s own
compose stack automatically once both are scaffolded in.

## Testing

`uv run pytest` — runs with `task_always_eager=True` (`tests/conftest.py`)
so `.delay()` executes inline against a shared in-memory sqlite engine, no
live broker or Postgres required for the unit suite
(`references/backend/celery.md`'s "Pitfalls & testing"). `fakeredis` is
pinned in the `dev` dependency group for a project that wants to exercise
`registry.py`'s producer path against a fake Redis instead of `memory://`.
Integration coverage against a real broker/worker process is a project's
own addition — run `docker-compose.yml`'s stack and dispatch a real task.

## Security

- **`task_serializer`/`accept_content` pinned to `json`** — never enable
  `pickle`; it executes arbitrary code on deserialize from an untrusted
  broker (`references/security/secure-baseline.md`, celery.md's
  "Serialization & security").
- **Non-root container** — the Dockerfile's `prod`/`dev` stages both run
  as a created, unprivileged `app` user (uid/gid 1000), matching
  `backend/fastapi`'s and `backend/django`'s identical posture.
- **No secret baked into the image** — `CELERY_BROKER_URL`/
  `CELERY_RESULT_BACKEND`/`DATABASE_URL` are all runtime environment,
  injected the same way the backend block's own secrets are (the infra
  block's ECS task `secrets`/`valueFrom`, or docker-compose env in dev) —
  never an `ARG`/`ENV` default in the Dockerfile.
- **Structured logs never carry secrets or full PII** — `JsonFormatter`
  does not redact by itself; a task author is responsible for not passing
  a secret as a log arg, same discipline the audit-logging component
  documents for the app.

## Maintenance

Celery/redis-py/django-celery-beat pins live in
`references/compatibility-matrix.md`'s "Backend — Python" row (this
block's `versions-pinned-to` target); `redis-py`'s exact resolved line is
constrained by `celery[redis]`'s own `kombu[redis]` dependency (currently
`<6.5` against Celery 5.6.x) — see that matrix row's own note before
bumping either independently. `app/core/db/session.py` is a byte-copy of
`templates/components/backend/db-session/session.py`, kept in sync via
the weekly freshness audit (Stage 12, #35) — never hand-edit it directly;
edit the source component and re-sync. `app/core/settings.py`'s
`AppSettings` class is the same vendored byte-copy convention from
`templates/components/backend/settings/settings.py`; `WorkerSettings` is
new, non-vendored code specific to this block.
