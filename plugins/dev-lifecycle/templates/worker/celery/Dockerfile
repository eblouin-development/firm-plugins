# Multi-stage image for this block. ONE image, TWO processes run from it
# (docker-compose.yml's `worker` and `beat` services both build from this
# file and only differ in CMD) — matching Celery's own "worker and beat
# are separate processes from the same codebase" model
# (references/backend/celery.md's "Periodic tasks" section: run EXACTLY
# ONE beat, any number of worker replicas).
#
# - `dev`  — `just dev` / docker-compose.yml's `target: dev`; bind-mounts
#            source so a host edit is picked up on the next task pickup
#            (Celery has no live-reload of its own — a dev loop restarts
#            the container/process to pick up a code change, same as any
#            other Python worker process; --autoreload-style tooling is
#            deliberately not added here to avoid a dev-only dependency).
# - `prod` — the hardened production image, and the LAST/default stage:
#            a `docker build` with no `--target` builds this stage, so
#            what ships and what trivy scans is always the hardened one.
#
# Base image and uv version both per references/compatibility-matrix.md:
# "Containers" (python:3.13-slim-bookworm, ghcr.io/astral-sh/uv:0.11.31) —
# same pins backend/fastapi and backend/django already use. No ARG/ENV
# ever carries a secret: secrets are injected at RUNTIME (the infra
# block's ECS task `secrets`/`valueFrom`, or docker-compose env), never
# baked into an image layer (references/security/secure-baseline.md).

FROM python:3.13-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

# `--no-dev`: this image runs the worker/beat process — it never runs the
# test suite, so the `dev` dependency-group (pytest/fakeredis/aiosqlite)
# has no reason to be inside it. No `uv.lock` committed (matches
# backend/fastapi's own posture) — `uv sync` resolves fresh in THIS layer.
RUN uv sync --no-dev

# Non-root (uid/gid 1000 — matches backend/fastapi's and the infra block's
# ECS task def convention): least privilege at runtime.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --home-dir /app --no-create-home app \
    && chown -R app:app /app /opt/venv
USER app

# --- dev: bind-mount + shorter, chattier log level -------------------------
FROM base AS dev

CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=INFO"]

# --- prod: hardened, default/final stage ------------------------------------
FROM base AS prod

# HEALTHCHECK targets the WORKER process by default; docker-compose.yml's
# `beat` service overrides both CMD and this HEALTHCHECK's test to
# `python -m app.health beat` — see app/health.py for both probes.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-m", "app.health", "worker"]

# `--concurrency` left at Celery's own default (CPU count via the prefork
# pool) — a project tunes it per its own task profile (celery.md's
# "Workers & concurrency"); `-Q` is left unset so this worker consumes
# BOTH the default and IO queues out of the box (a project scales a
# DEDICATED IO-queue worker replica by overriding CMD with `-Q io` once
# task volume warrants it, per celery.md's routing guidance).
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=INFO"]
