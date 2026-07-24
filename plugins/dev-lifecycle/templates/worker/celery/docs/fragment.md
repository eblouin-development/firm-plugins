<!-- fragment: block:worker/celery -->

## Setup
Materializes into `apps/worker/`, composing alongside whichever backend
block (`backend/fastapi` or `backend/django`) is scaffolded into
`apps/api/` — this block shares that backend's `DATABASE_URL`. Requires
Python 3.13.x + uv (`uv sync --all-groups`), `CELERY_BROKER_URL` (a
`redis://...` URL — required), and `CELERY_RESULT_BACKEND` (optional,
only if a task's return value is consumed). Run the worker with `uv run
celery -A app.celery_app worker --loglevel=INFO` and beat with `uv run
celery -A app.celery_app beat --loglevel=INFO` — or `docker compose up
--build` inside `apps/worker/` to boot worker + beat + their own Redis +
Postgres without a local Python install. Write new tasks in `app/tasks/`
using `app/tasks/base.py`'s `idempotent_task()` decorator (acks_late +
declarative retry/backoff by default) — see `app/tasks/example.py` for a
worked default-queue and IO-queue example. A backend route dispatches
work by copying `app/registry.py` into its own `app/core/tasks/
registry.py` and calling `enqueue(TaskName.<...>, ...)` — never call a
task function directly (defeats the whole point) and never import this
block's task code from the backend process (they're separate
deployables — see `app/registry.py`'s own docstring).

## Deployment
One Dockerfile serves both processes, via two DIFFERENT build stages —
`prod` (default, worker) and `beat` — each with its own `HEALTHCHECK`
(`python -m app.health worker` pings only this container's own node,
never a sibling replica's; `python -m app.health beat` checks the local
schedule file's freshness). Deploy **exactly one** `beat` replica (built
with `--target beat`, never scaled — two beats double-fire every
scheduled task) and any number of `worker` replicas (default `--target
prod`, or no `--target` at all). Wire each process's own health command
into the container health check on whichever orchestrator runs it — an
ECS task definition needs the matching command in its own `healthCheck`
block per `references/wiring/infra-app.md`; running the `prod` (worker)
image unmodified as a beat deployment is a mistake — it carries the
worker's probe, which beat will never satisfy.

## Secrets
| `CELERY_BROKER_URL` | worker/celery | Required, no default — the Redis broker connection string both `WorkerSettings` (worker/beat processes) and the copied-in `registry.py` (backend producer process) read. Point it at the shared Redis instance (this block's own `docker-compose.yml` for standalone dev, or the monorepo root compose's shared `redis` service once wired in). |
| `CELERY_RESULT_BACKEND` | worker/celery | Optional, default unset — only set it if a task's return value is actually consumed; a separate Redis DB index from the broker (e.g. `/1` vs `/0`) per `references/backend/redis.md`'s "Celery, testing" section. |

## Maintenance
Keep Celery/redis-py on the versions `references/compatibility-matrix.md`'s
"Backend — Python" row pins (redis-py's resolved version is constrained by
`celery[redis]`'s own `kombu[redis]` dependency — re-check before bumping
either independently). Run exactly one `beat` process. Tasks must stay
JSON-serializable (`task_serializer`/`accept_content` = `json`) — never
enable `pickle`. `app/core/db/session.py` is a byte-copy of
`templates/components/backend/db-session/session.py` — edit the source
component, not this file, and re-sync via the weekly freshness audit.
