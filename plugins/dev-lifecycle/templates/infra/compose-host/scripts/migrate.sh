#!/usr/bin/env bash
# Migrations on deploy, per references/devops/deploy-operate.md: an
# explicit, ordered step run against the NEW image, before that image
# starts serving traffic — never baked into the prod image's CMD (same
# posture as infra/aws-fargate's deploy.sh step 4, made concrete here
# because a single Docker host has no separate "run a one-off task"
# primitive — this runs the new image once, migrates, exits, and only THEN
# does the caller roll `api` over to it).
#
# Usage: scripts/migrate.sh <api-image-ref>
set -euo pipefail

IMAGE="${1:?usage: migrate.sh <api-image-ref>}"
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Running migrations via a one-off container from ${IMAGE}"
# `docker compose run` (not a raw `docker run` with a hand-derived network
# name) so the one-off container joins the SAME `internal` network Compose
# itself resolves the project to — correct even when COMPOSE_PROJECT_NAME
# or `docker compose -p <name>` overrides the default project-name-derived
# network name. --no-deps: don't also (re)start db/caddy/etc; --entrypoint
# sh: bypass the image's normal CMD to run the migrate command instead.
# API_IMAGE is set to the new image so this uses IT, not whatever's already
# rolled out. Adjust the migrate command for the project's backend track
# (alembic for FastAPI, manage.py for Django) — the fallback below only
# fires when `alembic` itself isn't on PATH (a Django image), not on an
# actual alembic failure, so a real migration error surfaces instead of
# being masked by a silent fallback attempt.
API_IMAGE="${IMAGE}" docker compose -f "${COMPOSE_DIR}/docker-compose.prod.yml" \
  --env-file "${COMPOSE_DIR}/.env" \
  run --rm --no-deps --entrypoint sh api \
  -c 'if command -v alembic >/dev/null 2>&1; then alembic upgrade head; else python manage.py migrate; fi'

echo "==> Migrations applied."
