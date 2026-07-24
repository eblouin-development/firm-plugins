<!--
recipe: background-jobs
applies-to:
  - worker block: worker/celery (templates/worker/celery/) — composes alongside either backend track
  - backend block: django (Celery + Redis broker — references/backend/celery.md's own reference stack) OR fastapi (worker/celery for anything beyond light fire-and-forget work; BackgroundTasks stays the right tool for in-process, best-effort work)
last-verified: 2026-07-24
provenance: manual
sources:
  - https://docs.celeryq.dev/en/stable/userguide/tasks.html
  - https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
  - https://fastapi.tiangolo.com/tutorial/background-tasks/
  - references/backend/celery.md
  - references/backend/fastapi.md
  - references/backend/redis.md
  - templates/worker/celery/README.md
-->

# Background jobs

Wire asynchronous task/worker execution so a request never blocks on
slow, retryable, or scheduled work: the `worker/celery` block
(`templates/worker/celery/`) for real, durable, retryable work on EITHER
backend track, and FastAPI's native `BackgroundTasks` for light
fire-and-forget work that can afford to be lost. Everything here is
**subordinate to the project's existing conventions** — when they
conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps (worker/celery, either backend)
- Wire-up steps (FastAPI + BackgroundTasks, for light work only)
- Choosing between BackgroundTasks and worker/celery
- Idempotent tasks, retries, and not blocking the request
- Doc fragment

## What this wires

Applying this recipe scaffolds `templates/worker/celery/` into a
project's `apps/worker/` — a Celery app, task-module conventions
(idempotent + retry/backoff + structured logging, `templates/worker/
celery/app/tasks/base.py`'s `idempotent_task()`), a beat scheduler, and an
enqueue seam (`app/registry.py`'s `TaskName`/`enqueue()`) either backend
copies in to dispatch work — then wires that seam into the feature that
needs async execution. It **composes existing pieces**:

- **`templates/worker/celery/README.md`** — the block's own composition
  contract, app layout, and conventions; this recipe wires a project's own
  feature to it, it does not restate the block's content.
- **`references/backend/celery.md`** — the kit's Celery convention doc
  (Celery 5.6.x): app setup/autodiscovery, `@shared_task` vs `@app.task`,
  `.delay()`/`.apply_async()`, `acks_late`/idempotency, declarative
  retries with backoff, routing/queues, periodic tasks, worker
  concurrency, and serialization security — the block embodies this doc,
  this recipe points at it for the underlying rationale.
- **`references/backend/redis.md`** — the broker (and optional result
  backend) the worker block runs against; also the pattern for a
  project's own Redis client if a task needs one directly (cache-aside,
  locks, pub/sub) beyond the Celery broker connection itself.
- **`references/backend/fastapi.md`**'s "Background work" section —
  `BackgroundTasks` for light, in-process, best-effort work; the
  worker/celery block for anything heavier. This recipe follows that same
  split rather than picking BackgroundTasks for everything.
- **The `idempotency` catalog component** (`templates/components/
  security/idempotency/`) — not itself a task-queue mechanism, but the
  same idempotency discipline (a stable operation key, safe replay) that
  makes a task safe to retry; see "Idempotent tasks" below for how the
  same principle applies inside a task body, not just at the HTTP
  boundary.

## Prerequisites
- **Either backend track:** the `worker/celery` block scaffolded into
  `apps/worker/`, alongside whichever backend block (`backend/fastapi` or
  `backend/django`) is already in `apps/api/` — they share `DATABASE_URL`.
  A reachable Redis instance for `CELERY_BROKER_URL` (the worker block's
  own `docker-compose.yml` for standalone dev, or the monorepo root
  compose's shared `redis` service once wired in — see
  `templates/monorepo/docker-compose.yml`).
- **The enqueue seam copied into the backend:** `templates/worker/celery/
  app/registry.py` copied into the backend block's own `app/core/tasks/
  registry.py` (or equivalent) — see the worker block README's "The
  enqueue seam" section. This is the ONLY worker-block file a backend
  needs; it never imports the worker's task code.
- **FastAPI track, light work only:** no new dependency —
  `BackgroundTasks` ships with FastAPI itself.

## Wire-up steps (worker/celery, either backend)
1. **Scaffold the block** into `apps/worker/` (copy `templates/worker/
   celery/` verbatim, matching how `backend/fastapi`/`backend/django`
   themselves get scaffolded into `apps/api/`). Set `CELERY_BROKER_URL`
   (required) and, only if a task's return value is consumed,
   `CELERY_RESULT_BACKEND` — both point at the project's Redis instance,
   resolved the same way every other runtime setting is (`WorkerSettings`
   in `app/core/settings.py`).
2. **Write the task** in `apps/worker/app/tasks/<module>.py`, decorated
   with `idempotent_task(name="app.tasks.<module>.<task>")` (`tasks/
   base.py`) — an upsert-shaped body (safe to run twice under
   `acks_late=True`), **IDs, not ORM objects**, as arguments
   (`celery.md`'s "Pitfalls & testing"). See `tasks/example.py` for a
   worked default-queue and IO-queue example.
3. **Copy `app/registry.py` into the backend block**, add the new task's
   name to `TaskName`, and call it from the route/view that triggers the
   work:
   ```python
   from app.core.tasks.registry import TaskName, enqueue

   @router.post("/widgets")
   async def create_widget(payload: WidgetCreate, db: AsyncSession = Depends(get_db)) -> WidgetOut:
       widget = await repo.create(**payload.model_dump())
       enqueue(TaskName.NOTIFY_WIDGET_CREATED, str(widget.id))
       return WidgetOut.model_validate(widget)
   ```
   Never call the task function directly and never import the worker
   block's task code from the backend process — `enqueue()`/`send_task`
   is the only path, matching `apps/api` and `apps/worker` being two
   separate deployables.
4. **Isolate slow/IO-heavy tasks by naming them `io_<something>`**
   (`celery_app.py`'s `_route_task` routes them onto the dedicated IO
   queue automatically) so a burst of slow tasks can't starve fast ones
   on the default queue — see `celery.md`'s "Routing & queues" for the
   underlying convention.
5. **For scheduled/periodic work**, add an entry to `celery_app.py`'s
   `beat_schedule` dict (the default file-based `PersistentScheduler`,
   works with either backend, no extra dependency) — or, on the Django
   track, opt into `django-celery-beat`'s DB-backed `DatabaseScheduler`
   for admin-editable schedules (worker block README's "Beat scheduler"
   section). Run **exactly one** `beat` process — two double-fire every
   scheduled task.

## Wire-up steps (FastAPI + BackgroundTasks, for light work only)
1. **Reach for `BackgroundTasks` only for light, fire-and-forget work
   tied to one request** — per `references/backend/fastapi.md`'s
   "Background work" section: e.g. writing a non-critical audit-adjacent
   log line. Add the parameter to the route handler and schedule the
   callable; it runs after the response is sent, in the same process.
   ```python
   from fastapi import BackgroundTasks

   @router.post("/widgets")
   async def create_widget(payload: WidgetCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> WidgetOut:
       widget = await repo.create(**payload.model_dump())
       background_tasks.add_task(notify_widget_created, widget.id)
       return WidgetOut.model_validate(widget)
   ```
2. **Know the limits before reaching for it on anything heavier.**
   `BackgroundTasks` runs **in-process**, with no retry, no persistence,
   and no cross-process durability — a worker restart or crash between
   "response sent" and "task finished" silently drops the work, and there
   is no dashboard, dead-letter handling, or backoff. Anything the
   project cannot afford to silently lose (payment follow-up, an
   irreversible external side effect, anything that must survive a
   restart) belongs on `worker/celery` instead — see "Choosing between"
   below.
3. **The same non-blocking discipline `templates/components/security/
   auth/`'s `EmailSender` seam already follows applies here**: don't
   `await` a slow network call synchronously inside the request path just
   because `BackgroundTasks` exists — catch and log its own errors; never
   propagate into a place nothing awaits it.

## Choosing between BackgroundTasks and worker/celery
| | `BackgroundTasks` | `worker/celery` |
| --- | --- | --- |
| Durability | None — lost on crash/restart | Durable — survives a worker crash (with `acks_late`) |
| Retries | None | Declarative, exponential backoff + jitter |
| Scheduling | None | `beat` — cron-like periodic tasks |
| Cross-process | No — runs in the API process | Yes — separate `apps/worker` process(es), scales independently |
| Right for | Cheap, best-effort, fine-to-lose work tied to one request | Anything retryable, scheduled, or that must not be silently dropped |

`BackgroundTasks` remains the right default for light work on the
FastAPI track — this recipe does not remove it, it adds the missing
heavier option both tracks now share.

## Idempotent tasks, retries, and not blocking the request
- **Idempotency**: `acks_late=True` + `reject_on_worker_lost=True`
  (`idempotent_task()`'s defaults) means a task can run **twice** under a
  worker crash — only safe because every task written through this
  decorator is upsert-shaped by convention (a stable key, not "increment
  a counter"). The same principle governs a `BackgroundTasks` callable
  that might legitimately fire on a retried request — write it so running
  twice produces the same end state, not a duplicated side effect.
- **Retries**: `idempotent_task()`'s declarative `autoretry_for`/
  `retry_backoff`/`retry_backoff_max`/`retry_jitter` defaults (override
  per task) over hand-rolled `try`/`except` — exponential backoff with
  jitter avoids a thundering-herd retry storm against a struggling
  downstream dependency.
- **Not blocking the request**: this is the entire point of both halves
  of this recipe — `enqueue()`/`.apply_async()` dispatches and returns
  immediately; `BackgroundTasks` schedules its callable to run only after
  the response has already been sent. Never call a task function directly
  (`sync_order(1)` instead of `enqueue(TaskName.SYNC_ORDER, 1)`) — that
  executes it synchronously in the request path, silently defeating the
  whole mechanism.

## Doc fragment
The portable fragment this recipe contributes to the project's root
README when applied:

```markdown
### Background jobs
- **Setup:** Retryable/scheduled/durable async work runs as Celery tasks (`idempotent_task()`-decorated, `templates/worker/celery/app/tasks/`) against a Redis broker in the `apps/worker` process, dispatched via `enqueue(TaskName.<...>, ...)` from either backend — never called directly. Slow/IO-bound tasks (named `io_*`) route to a dedicated queue automatically. Scheduled work uses `beat` (`beat` runs as exactly one process, never more) — file-based by default, DB-backed (`django-celery-beat`) as an opt-in on the Django track.
- **Setup (light work):** Fire-and-forget work tied to one request that can afford to be lost still uses FastAPI's `BackgroundTasks` — in-process, best-effort, no retry/persistence.
- **Secrets:** `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` point at the project's Redis instance, resolved the same way as other runtime config — see `templates/worker/celery/docs/fragment.md`.
- **Maintenance:** Keep Celery/redis-py on `references/compatibility-matrix.md`'s pins (redis-py's exact line is constrained by Celery's own `kombu[redis]` dependency — don't pin it independently). Run exactly one `beat` process. Tasks must stay JSON-serializable (`task_serializer`/`accept_content` = `json`) — never enable `pickle`.
```

---
<!--
Recipe authored via the `recipe-author` skill, rewritten for issue #100:
the worker/celery block (templates/worker/celery/) now exists, closing the
FastAPI-track gap this recipe used to document honestly as a "project
addition." The Django track's existing Celery posture
(references/backend/celery.md) is unchanged in substance — the recipe now
wires the SAME block for both tracks instead of describing two divergent
paths.
-->
